"""F09 typed_transition_and_waiting_time_inventory RED analytic tests."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.event_models import RootEvent, RootEvents, RootEventSettings
from lnt.characterization.f09_ordering import compute_f09_event_ordering
from lnt.characterization.f09_result import (
    DEAD_TIME_OVERLAP,
    DECLARED_CODES,
    GAPS_PRESENT,
    INSUFFICIENT_EVENTS,
    METHOD,
    SINGLE_CYCLE_RECORD,
    F09Result,
)
from lnt.characterization.records import Inference, Status, Unit, validate_unit_name
from lnt.events.models import Polarity, UnqualifiedGap

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.characterization.event_models import RootTimelineItem

FS_HZ: Final = 1000.0
RECORD_SAMPLES: Final = 10_000
DEAD_TIME_S: Final = 0.0001
CLUSTER_GAP_S: Final = 0.02
MINIMUM_EVENT_COUNT: Final = 5
MAXIMUM_EVENTS: Final = 4096
EVENT_TYPE_FIELDS: Final = ("polarity", "dominant_band")
DEAD_TIME_HANDLING: Final = "exclude_intervals"
GAP_HANDLING: Final = "exclude_waiting_intervals"
POISSON_COUNT: Final = 2000
POISSON_SEED: Final = 6022

EXPECTED_CODES: Final = frozenset(
    {
        "insufficient_events",
        "dead_time_overlap",
        "single_cycle_record",
        "gaps_present",
    }
)


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=262_144,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4096,
        max_surrogates=19,
        deterministic_seed=6022,
    )


@dataclass(frozen=True, slots=True)
class _Declared:
    """Объявленные гейты рецепта в одном месте; тест переопределяет по одному."""

    event_type_fields: tuple[str, ...] = EVENT_TYPE_FIELDS
    cluster_gap_s: float = CLUSTER_GAP_S
    minimum_event_count: int = MINIMUM_EVENT_COUNT
    dead_time_handling: str = DEAD_TIME_HANDLING
    gap_handling: str = GAP_HANDLING
    maximum_events: int = MAXIMUM_EVENTS
    resources: ResourceLimits = field(default_factory=_resources)


def _settings(*, dead_time_s: float = DEAD_TIME_S) -> RootEventSettings:
    """Настройки корневого инвентаря: заявлены один раз для всех сценариев."""
    return RootEventSettings(
        recipe_sha256="0" * 64,
        detector="existing_event_inventory",
        noise_window_samples=4001,
        noise_step_samples=1000,
        minimum_noise_samples=2000,
        threshold_sigma=5.0,
        max_gap_samples=10,
        minimum_event_samples=3,
        minimum_snr_db=10.0,
        minimum_snr_ratio=10.0 ** (10.0 / 20.0),
        dead_time_s=dead_time_s,
        dead_time_samples=1,
        chunk_samples=4096,
        fft_max_samples=4096,
        clipping_low_v=-0.5,
        clipping_high_v=0.5,
        clipping_reason_code=None,
        dead_time_handling=DEAD_TIME_HANDLING,
        gap_handling="exclude_crossing_intervals",
    )


def _event(
    peak_s: float,
    polarity: Polarity,
    band: str | None,
    *,
    ordinal: int = 0,
    segment: int = 0,
    boundary: bool = False,
) -> RootEvent:
    """RootEvent по образцу F02/F05: спаны и времена задаются явно, без детектора."""
    peak = round(peak_s * FS_HZ)
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=segment,
        start_sample=peak,
        end_sample=peak,
        peak_sample=peak,
        start_time_s=peak / FS_HZ,
        end_time_s=peak / FS_HZ,
        peak_time_s=peak / FS_HZ,
        peak_value_v=1.0,
        polarity=polarity,
        snr_ratio=100.0,
        excess_v2_s=0.0,
        v2_s=0.0,
        clipped=False,
        dominant_band=band,
        dominant_band_reason_code=None if band else "dominant_band_insufficient_support",
        boundary=boundary,
    )


def _no_replay(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
    """Пустой реплей: тесты F09 читают готовые префиксы, а не переигрывают запись."""
    return iter(())


def _inventory(
    events: tuple[RootEvent, ...],
    *,
    gaps: tuple[UnqualifiedGap, ...] = (),
    gap_count: int = 0,
    omitted_gap_count: int = 0,
    dead_time_rejected_count: int = 0,
    omitted_exclusion_count: int = 0,
    accepted_count: int | None = None,
) -> RootEvents:
    """Готовый корневой инвентарь: движок F09 обязан читать его, а не пересчитывать."""
    return RootEvents(
        sample_rate_hz=FS_HZ,
        sample_count=RECORD_SAMPLES,
        events=events,
        gaps=gaps,
        exclusions=(),
        candidate_count=len(events) + dead_time_rejected_count,
        snr_rejected_count=0,
        accepted_count=len(events) if accepted_count is None else accepted_count,
        omitted_count=0,
        dead_time_rejected_count=dead_time_rejected_count,
        gap_count=gap_count,
        omitted_gap_count=omitted_gap_count,
        omitted_exclusion_count=omitted_exclusion_count,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=_settings(),
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=_no_replay,
    )


def _evaluate(inventory: RootEvents, **overrides: object) -> F09Result:
    declared = replace(_Declared(), **overrides)
    return compute_f09_event_ordering(
        inventory,
        event_type_fields=declared.event_type_fields,
        cluster_gap_s=declared.cluster_gap_s,
        minimum_event_count=declared.minimum_event_count,
        dead_time_handling=declared.dead_time_handling,
        gap_handling=declared.gap_handling,
        maximum_events=declared.maximum_events,
        resources=declared.resources,
    )


def _labels(result: F09Result) -> tuple[tuple[str, str, int], ...]:
    """Переходы как обычные кортежи: сравнение с аналитической истиной без объектов."""
    return tuple((item.source, item.target, item.count) for item in result.transitions)


def _synthesized() -> RootEvents:
    """Пять событий с известными типами и интервалами: dt = 50/44/60/50 мс."""
    positive, negative = Polarity.POSITIVE, Polarity.NEGATIVE
    return _inventory(
        (
            _event(0.000, positive, "band_low", ordinal=1),
            _event(0.050, positive, "band_low", ordinal=2),
            _event(0.094, negative, "band_low", ordinal=3),
            _event(0.154, positive, "band_high", ordinal=4),
            _event(0.204, negative, "band_high", ordinal=5),
        )
    )


def _burst_sequence() -> RootEvents:
    """Два кластера по три события: разрыв 90 мс против объявленных 20 мс."""
    positive = Polarity.POSITIVE
    times = (0.000, 0.005, 0.010, 0.100, 0.105, 0.110)
    return _inventory(
        tuple(
            _event(time_s, positive, "band_low", ordinal=index)
            for index, time_s in enumerate(times, start=1)
        )
    )


def _poisson_inventory() -> RootEvents:
    """Пуассоновский поток: типы независимы от интервалов, порядок не задан."""
    rng = np.random.default_rng(POISSON_SEED)
    times = np.cumsum(rng.exponential(1.0 / 50.0, size=POISSON_COUNT))
    polarities = (Polarity.POSITIVE, Polarity.NEGATIVE, Polarity.BIPOLAR)
    bands = ("band_a", "band_b", "band_c")
    return _inventory(
        tuple(
            _event(
                float(times[index]),
                polarities[int(rng.integers(0, 3))],
                bands[int(rng.integers(0, 3))],
                ordinal=index,
            )
            for index in range(POISSON_COUNT)
        )
    )


def test_method_matches_the_declared_recipe_method() -> None:
    assert METHOD == "typed_transition_and_waiting_time_inventory"


def test_reason_code_vocabulary_is_closed() -> None:
    """Словарь F09 закрыт: ровно четыре публичных кода из спеки:461-462."""
    assert DECLARED_CODES == (
        INSUFFICIENT_EVENTS,
        DEAD_TIME_OVERLAP,
        SINGLE_CYCLE_RECORD,
        GAPS_PRESENT,
    )
    assert set(DECLARED_CODES) == EXPECTED_CODES


def test_synthesized_sequence_reproduces_exact_transitions_and_dt() -> None:
    """Положительное из спеки:466-468: точные переходы n_ij и точные dt."""
    result = _evaluate(_synthesized())
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.event_labels == (
        "positive|band_low",
        "positive|band_low",
        "negative|band_low",
        "positive|band_high",
        "negative|band_high",
    )
    assert _labels(result) == (
        ("positive|band_low", "positive|band_low", 1),
        ("positive|band_low", "negative|band_low", 1),
        ("negative|band_low", "positive|band_high", 1),
        ("positive|band_high", "negative|band_high", 1),
    )
    assert list(result.dt_s) == [pytest.approx(v) for v in (0.050, 0.044, 0.060, 0.050)]
    assert (result.sample_count, result.observation_count) == (5, 5)
    assert (result.missing_count, result.stored_count) == (0, 5)
    assert (result.start_s, result.end_s) == (pytest.approx(0.000), pytest.approx(0.204))


def test_cluster_threshold_splits_bursts_and_keeps_raw_intervals() -> None:
    """Кластеры по объявленным 20 мс: разрыв 90 мс режет поток, но dt остаётся сырым."""
    result = _evaluate(_burst_sequence())
    assert result.status is Status.AVAILABLE
    assert list(result.dt_s) == [pytest.approx(v) for v in (0.005, 0.005, 0.090, 0.005, 0.005)]
    assert list(result.cluster_sizes) == [3, 3]
    assert list(result.cluster_start_s) == [pytest.approx(0.000), pytest.approx(0.100)]
    assert list(result.cluster_spread_s) == [pytest.approx(0.010), pytest.approx(0.010)]
    assert result.cluster_count == 2


def test_polarity_run_lengths_are_exact() -> None:
    """Серии равной полярности (спека:448): P,P,N,P,N,N дают ровно 2,1,1,2."""
    positive, negative = Polarity.POSITIVE, Polarity.NEGATIVE
    times = (0.000, 0.050, 0.100, 0.150, 0.200, 0.250)
    polarities = (positive, positive, negative, positive, negative, negative)
    events = tuple(
        _event(time_s, polarity, "band_low", ordinal=index)
        for index, (time_s, polarity) in enumerate(zip(times, polarities, strict=True), start=1)
    )
    result = _evaluate(_inventory(events))
    assert list(result.polarity_run_lengths) == [2, 1, 1, 2]


def test_below_minimum_event_count_is_unavailable_without_fabricated_quantities() -> None:
    """Четыре события при минимуме пять: отказ, а не пары переходов из ничего."""
    positive = Polarity.POSITIVE
    events = tuple(
        _event(0.050 * index, positive, "band_low", ordinal=index) for index in range(1, 5)
    )
    result = _evaluate(_inventory(events))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (INSUFFICIENT_EVENTS,)
    assert result.event_labels == ()
    assert result.transitions == ()
    assert result.dt_s.size == 0
    assert result.polarity_run_lengths.size == 0
    assert result.cluster_sizes.size == 0
    assert (result.sample_count, result.observation_count) == (4, 0)
    assert (result.missing_count, result.stored_count) == (4, 0)
    assert result.start_s is None
    assert result.end_s is None


def test_dead_time_exclusions_reduce_support_and_are_flagged() -> None:
    """Лимит из спеки:471-472: наложения в мёртвом времени не считаются событиями.

    Корень уже снял двух кандидатов: `candidate_count = 8`, а принятых и
    сохранённых — 6, поэтому поддержка F09 честно равна 6, а сокращение видно
    в паре `candidate_count`/`sample_count`, а не растворяется в счётчиках.
    """
    positive = Polarity.POSITIVE
    events = tuple(
        _event(0.050 * index, positive, "band_low", ordinal=index) for index in range(1, 7)
    )
    inventory = _inventory(events, dead_time_rejected_count=2)
    result = _evaluate(inventory)
    assert result.status is Status.PARTIAL
    assert result.reason_codes == (DEAD_TIME_OVERLAP,)
    assert result.dead_time_rejected_count == 2
    assert result.dead_time_omitted_count == 0
    assert result.candidate_count == 8
    assert result.dead_time_s == pytest.approx(DEAD_TIME_S)
    assert result.observation_count == 6
    assert result.sample_count == 6
    assert result.missing_count == 0
    assert result.dt_s.size == 5
    assert len(result.event_labels) == 6


def test_gap_crossing_intervals_are_excluded_from_waiting_times() -> None:
    """Пропуски (спека:449-451): dt через несогласованный интервал не публикуется.

    Интервал 0.010 → 0.300 с перепрыгивает несогласованный участок, поэтому в
    серии остаются четыре dt по 0.005 с, а разрыв исключён, а не засчитан.
    """
    positive = Polarity.POSITIVE
    times = (0.000, 0.005, 0.010, 0.300, 0.305, 0.310)
    segments = (0, 0, 0, 1, 1, 1)
    events = tuple(
        _event(time_s, positive, "band_low", ordinal=index, segment=segment)
        for index, (time_s, segment) in enumerate(zip(times, segments, strict=True), start=1)
    )
    gap = UnqualifiedGap(start_sample=150, end_sample=200, start_time_s=0.150, end_time_s=0.200)
    inventory = _inventory(events, gaps=(gap,), gap_count=1)
    result = _evaluate(inventory)
    assert result.status is Status.PARTIAL
    assert result.reason_codes == (GAPS_PRESENT,)
    assert result.gap_count == 1
    assert result.dt_s.size == 4
    assert list(result.dt_s) == [pytest.approx(v) for v in (0.005, 0.005, 0.005, 0.005)]
    assert list(result.cluster_sizes) == [3, 3]


def test_single_cluster_record_is_flagged_and_thesis_is_stated() -> None:
    """Пробел спеки:458-459: одна пачка в записи — не независимые повторы."""
    positive = Polarity.POSITIVE
    events = tuple(
        _event(0.005 * index, positive, "band_low", ordinal=index) for index in range(1, 9)
    )
    result = _evaluate(_inventory(events))
    assert result.status is Status.PARTIAL
    assert result.reason_codes == (SINGLE_CYCLE_RECORD,)
    assert result.cluster_count == 1
    assert list(result.cluster_spread_s) == [pytest.approx(0.035)]
    assert result.inference.estimate_scope == "single_session_descriptive"
    assert result.inference.population_inference == "withheld"
    assert result.inference.reason_code == "independent_capture_units_required"


def test_boundary_events_are_counted_and_never_dropped_silently() -> None:
    """Границы записи (спека:449-451): флаг публикуется, пиковые времена остаются."""
    positive = Polarity.POSITIVE
    events = tuple(
        _event(
            0.050 * index,
            positive,
            "band_low",
            ordinal=index,
            boundary=index in {1, 6},
        )
        for index in range(1, 7)
    )
    result = _evaluate(_inventory(events))
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.boundary_event_count == 2
    assert result.boundary_handling == "boundary_flag_only_not_dropped"
    assert len(result.event_labels) == 6
    assert result.dt_s.size == 5


def test_unavailable_dominant_band_keeps_the_declared_reason_label() -> None:
    """Полоса не квалифицирована: в метке остаётся объявленная причина, не выдумка."""
    positive = Polarity.POSITIVE
    events = tuple(_event(0.050 * index, positive, None, ordinal=index) for index in range(1, 7))
    result = _evaluate(_inventory(events))
    assert result.unclassified_band_count == 6
    assert set(result.event_labels) == {"positive|dominant_band_insufficient_support"}


def test_maximum_events_caps_stored_events_and_counts_omitted() -> None:
    """Лимит хранения из спеки:454: кап режет публикацию, но не считается молча."""
    positive = Polarity.POSITIVE
    events = tuple(
        _event(0.050 * index, positive, "band_low", ordinal=index) for index in range(1, 7)
    )
    result = _evaluate(_inventory(events), maximum_events=4)
    assert result.status is Status.AVAILABLE
    assert result.omitted_event_count == 2
    assert len(result.event_labels) == 4
    assert result.dt_s.size == 3
    assert result.observation_count == 4
    assert result.sample_count == 6


def test_poisson_events_show_near_uniform_transitions_and_geometric_runs() -> None:
    """Контроль спеки:469-470: пуассоновский поток не даёт детерминированного порядка.

    Тип это пара независимых осей (3 полярности × 3 полосы), поэтому ячеек 81,
    а ожидание `(n-1)/81 = 24.68` с сигмой `sqrt(24.68) = 4.97`. Замерено для
    этого семени: заполнены все 81 ячейка, максимум отклонения 17.3 против
    четырёхсигмовой границы 19.9, то есть ни одна ячейка не выделена. Геометрия
    серий ПОЛЯРНОСТИ: при трёх равновероятных полярностях `p(1)=2/3` и среднее
    `1.5`; замерено 0.669 и 1.537 при 1338 сериях, допуски 0.05 и 0.10 покрывают
    выборочный разброс `sqrt(2/R)`.
    """
    count = POISSON_COUNT
    result = _evaluate(_poisson_inventory())
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    counts = {(item.source, item.target): item.count for item in result.transitions}
    assert len(counts) == 81
    expected = (count - 1) / 81.0
    bound = 4.0 * float(np.sqrt(expected))
    assert max(abs(value - expected) for value in counts.values()) <= bound
    polarity = np.asarray(result.polarity_run_lengths, dtype=np.float64)
    assert polarity.size == 1338
    assert abs(float(np.mean(polarity == 1)) - 2.0 / 3.0) <= 0.05
    assert abs(float(np.mean(polarity)) - 1.5) <= 0.10


def test_deterministic_cycle_is_visible_yet_no_verdict_is_published() -> None:
    """Мера видит строгий порядок, но движок не публикует ни p-value, ни CI."""
    cycle = 3
    events = tuple(
        _event(
            0.050 * index,
            (
                Polarity.POSITIVE,
                Polarity.NEGATIVE,
                Polarity.BIPOLAR,
            )[index % cycle],
            "band_low",
            ordinal=index,
        )
        for index in range(1, 2002)
    )
    result = _evaluate(_inventory(events))
    counts = {(item.source, item.target): item.count for item in result.transitions}
    assert len(counts) == 3
    assert sorted(counts.values()) == [666, 667, 667]
    assert set(counts) == {
        ("positive|band_low", "negative|band_low"),
        ("negative|band_low", "bipolar|band_low"),
        ("bipolar|band_low", "positive|band_low"),
    }
    names = {item.name for item in dataclasses.fields(F09Result)}
    assert not any("p_value" in name or "confidence" in name for name in names)
    assert result.inference.population_inference == "withheld"


def test_runs_are_deterministic_field_by_field() -> None:
    first = _evaluate(_synthesized())
    second = _evaluate(_synthesized())
    assert first.status is second.status
    assert first.reason_codes == second.reason_codes
    assert first.event_labels == second.event_labels
    assert _labels(first) == _labels(second)
    assert np.array_equal(first.dt_s, second.dt_s)
    assert np.array_equal(first.polarity_run_lengths, second.polarity_run_lengths)
    assert np.array_equal(first.cluster_spread_s, second.cluster_spread_s)
    assert first.inference == second.inference


def test_resources_are_accepted_and_unspent() -> None:
    """Бюджет объявлен, но не тратится: работа O(E log E) + O(E) (спека:464)."""
    small = ResourceLimits(
        chunk_samples=4096,
        hard_max_chunk_samples=8192,
        max_work_bytes=1_000_000,
        max_artifact_bytes=100_000,
        max_stored_trajectories=64,
        max_surrogates=19,
        deterministic_seed=1,
    )
    baseline = _evaluate(_synthesized())
    limited = _evaluate(_synthesized(), resources=small)
    assert np.array_equal(baseline.dt_s, limited.dt_s)
    assert _labels(baseline) == _labels(limited)
    assert baseline.status is limited.status


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("cluster_gap_s", 0.0),
        ("cluster_gap_s", -0.02),
        ("cluster_gap_s", float("nan")),
        ("cluster_gap_s", float("inf")),
        ("minimum_event_count", 0),
        ("minimum_event_count", -5),
        ("maximum_events", 0),
        ("maximum_events", -1),
    ],
)
def test_invalid_numeric_inputs_raise_valueerror(field_name: str, value: float) -> None:
    """Невалидные числа — ValueError (прецедент F04/F07), не тихий отказ."""
    with pytest.raises(ValueError, match=field_name):
        _evaluate(_synthesized(), **{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("event_type_fields", ()),
        ("event_type_fields", ("dominant_band",)),
        ("event_type_fields", ("polarity", "amplitude_v")),
        ("dead_time_handling", "count_intervals"),
        ("gap_handling", "include_waiting_intervals"),
    ],
)
def test_undeclared_rules_are_refused(field_name: str, value: object) -> None:
    """Незалоченные правила и поля типов движком не поддерживаются — явный отказ."""
    with pytest.raises(ValueError, match=field_name):
        _evaluate(_synthesized(), **{field_name: value})


def test_result_is_frozen() -> None:
    result = _evaluate(_synthesized())
    with pytest.raises(dataclasses.FrozenInstanceError):
        F09Result.__setattr__(result, "status", Status.UNAVAILABLE)


def test_thesis_record_rejects_population_inference() -> None:
    """Тезис спеки:458-459 обеспечивается общим типом, а не комментарием."""
    with pytest.raises(CharacterizationError):
        Inference(
            estimate_scope="single_session_descriptive",
            population_inference="estimated",
            reason_code="independent_capture_units_required",
        )


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("dt_s", Unit.S),
        ("cluster_spread_s", Unit.S),
        ("cluster_start_s", Unit.S),
        ("transition_counts", Unit.COUNT),
        ("polarity_run_lengths", Unit.COUNT),
        ("cluster_sizes", Unit.COUNT),
    ],
)
def test_persisted_names_match_the_declared_units(name: str, unit: Unit) -> None:
    """Единицы публикуемых величин принимаются словарём единиц."""
    validate_unit_name(name, unit)
