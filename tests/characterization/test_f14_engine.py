"""Аналитические тесты движка F14 cross-channel association."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.event_models import (
    RootEvent,
    RootEvents,
    RootEventSettings,
    RootTimelineItem,
    TaggedEvent,
    TaggedGap,
)
from lnt.characterization.f14_engine import compute_f14_cross_channel_event_association
from lnt.characterization.f14_result import (
    CHANNEL_MISSING,
    DECLARED_CODES,
    GAPS_PRESENT,
    LAG_SIGN_CONVENTION,
    METHOD,
    WINDOW_TRUNCATED,
    F14Declarations,
)
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status
from lnt.events.models import Polarity, UnqualifiedGap

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def test_locked_f14_declaration_matches_authoritative_recipe() -> None:
    """Метод и замороженные поля F14 совпадают с рецептом v2."""
    declarations = F14Declarations.locked()

    assert METHOD == "bidirectional_event_triggered_cross_channel_association"
    assert LAG_SIGN_CONVENTION == "target_after_trigger_positive"
    assert F14Declarations.locked().phase_bins == 64
    assert declarations.trigger_window_low_s == -0.02
    assert declarations.trigger_window_high_s == 0.02
    assert declarations.relative_time_bins == 401
    assert declarations.nearest_event_lag_low_s == -0.02
    assert declarations.nearest_event_lag_high_s == 0.02
    assert declarations.nearest_event_tie_break == "earlier_target"
    assert declarations.phase_bins == 64
    assert declarations.cycle_shift_offsets == tuple(range(1, 33))
    assert declarations.minimum_triggers == 20
    assert declarations.maximum_triggers_per_direction == 4096
    assert declarations.boundary_handling == "exclude_incomplete_windows"


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=128,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=19,
        deterministic_seed=6_022,
    )


def test_missing_channel_returns_unavailable_with_empty_domains() -> None:
    """Отсутствующий канал получает ровно объявленный код без нулевых измерений."""
    result = compute_f14_cross_channel_event_association(
        phase=None,
        ch1_samples=None,
        ch1_phase_means=None,
        ch1_events=None,
        ch2_samples=None,
        ch2_phase_means=None,
        ch2_events=None,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("channel_missing",)
    assert result.relative_time_s.size == 0
    assert all(direction.mean_waveform_v.size == 0 for direction in result.directions)
    assert all(direction.event_probability.size == 0 for direction in result.directions)
    assert all(direction.baseline_probability.size == 0 for direction in result.directions)


def _phase(sample_count: int = 6_400) -> PhaseCycles:
    starts = np.arange(0, sample_count, 100, dtype=np.float64)
    return PhaseCycles(
        sample_rate_hz=1_000.0,
        sample_count=sample_count,
        cycle_start_samples=starts,
        cycle_end_samples=starts + 100.0,
        cycle_valid=np.ones(starts.size, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _means(sample_count: int = 6_400, value: float = 0.0) -> PhaseMeans:
    return PhaseMeans(
        means_v=np.full(64, value, dtype=np.float64),
        counts=np.full(64, sample_count, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _event(sample: int, ordinal: int, *, boundary: bool = False) -> RootEvent:
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=0,
        start_sample=sample - 1,
        end_sample=sample + 1,
        peak_sample=sample,
        start_time_s=(sample - 1) / 1_000.0,
        end_time_s=(sample + 1) / 1_000.0,
        peak_time_s=sample / 1_000.0,
        peak_value_v=1.0,
        polarity=Polarity.POSITIVE,
        snr_ratio=10.0,
        excess_v2_s=0.001,
        v2_s=0.002,
        clipped=False,
        dominant_band="band_0001",
        dominant_band_reason_code=None,
        boundary=boundary,
    )


def _inventory(
    events: tuple[RootEvent, ...], sample_count: int, gaps: tuple[UnqualifiedGap, ...] = ()
) -> RootEvents:
    def replay(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        for event in events:
            yield TaggedEvent("event", event)
        for gap in gaps:
            yield TaggedGap("gap", gap)

    settings = RootEventSettings(
        recipe_sha256="test",
        detector="existing_event_inventory",
        noise_window_samples=2_048,
        noise_step_samples=1_024,
        minimum_noise_samples=1_024,
        threshold_sigma=5.0,
        max_gap_samples=4,
        minimum_event_samples=1,
        minimum_snr_db=10.0,
        minimum_snr_ratio=3.9810717055349722,
        dead_time_s=0.001,
        dead_time_samples=1,
        chunk_samples=128,
        fft_max_samples=4_096,
        clipping_low_v=None,
        clipping_high_v=None,
        clipping_reason_code="not_applicable",
        dead_time_handling="exclude_intervals",
        gap_handling="exclude_crossing_intervals",
    )
    return RootEvents(
        sample_rate_hz=1_000.0,
        sample_count=sample_count,
        events=events,
        gaps=gaps,
        exclusions=(),
        candidate_count=len(events),
        snr_rejected_count=0,
        accepted_count=len(events),
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=len(gaps),
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=replay,
    )


def test_non_synchronous_channels_return_exact_code() -> None:
    """Разные длины или частоты каналов не смешиваются в общей сетке."""
    phase = _phase(4)
    means = _means(4)
    ch1 = np.zeros(4, dtype=np.float64)
    ch2 = np.zeros(3, dtype=np.float64)
    result = compute_f14_cross_channel_event_association(
        phase=phase,
        ch1_samples=ch1,
        ch1_phase_means=means,
        ch1_events=_inventory((), 4),
        ch2_samples=ch2,
        ch2_phase_means=means,
        ch2_events=_inventory((), 3),
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("channels_not_synchronous",)


def test_paired_events_recover_both_directions_and_lag_sign() -> None:
    """Известная задержка видна в обоих направлениях без физического вывода о лидере."""
    sample_count = 6_400
    ch1 = np.zeros(sample_count, dtype=np.float64)
    ch2 = np.zeros(sample_count, dtype=np.float64)
    ch1_events: list[RootEvent] = []
    ch2_events: list[RootEvent] = []
    for ordinal in range(20):
        first = 40 + ordinal * 100
        second = first + 3
        ch1[first] = 2.0
        ch2[second] = 3.0
        ch1_events.append(_event(first, ordinal + 1))
        ch2_events.append(_event(second, ordinal + 1))
    first_inventory = _inventory(tuple(ch1_events), sample_count)
    second_inventory = _inventory(tuple(ch2_events), sample_count)
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=ch1,
        ch1_phase_means=_means(sample_count),
        ch1_events=first_inventory,
        ch2_samples=ch2,
        ch2_phase_means=_means(sample_count),
        ch2_events=second_inventory,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.relative_time_s.shape == (401,)
    forward, reverse = result.directions
    assert forward.baseline_probability.shape == (32, 401)
    assert (forward.trigger_channel, forward.response_channel) == ("ch1", "ch2")
    assert (reverse.trigger_channel, reverse.response_channel) == ("ch2", "ch1")
    assert forward.nearest_lag_s == pytest.approx(np.full(20, 0.003))
    assert reverse.nearest_lag_s == pytest.approx(np.full(20, -0.003))
    assert forward.event_probability.max() == 1.0
    assert reverse.event_probability.max() == 1.0
    assert 0.001 <= result.relative_time_s[int(np.argmax(forward.event_probability))] <= 0.004
    assert -0.005 <= result.relative_time_s[int(np.argmax(reverse.event_probability))] <= -0.002


def test_mean_waveform_subtracts_declared_phase_mean() -> None:
    """Средняя форма ответа равна нулю после вычитания фазового среднего."""
    sample_count = 6_400
    samples = np.full(sample_count, 2.0, dtype=np.float64)
    events = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    inventory = _inventory(events, sample_count)
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count, value=2.0),
        ch1_events=inventory,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count, value=2.0),
        ch2_events=inventory,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.directions[0].mean_waveform_v == pytest.approx(np.zeros(401), abs=1e-12)
    assert result.directions[1].mean_waveform_v == pytest.approx(np.zeros(401), abs=1e-12)


@pytest.mark.parametrize("code", sorted(PHASE_ROOT_REASON_CODES))
def test_phase_root_codes_normalize_to_declared_f14_code(code: str) -> None:
    """Каждый upstream phase-root reason сворачивается в F14 reference code."""
    sample_count = 6_400
    phase = replace(_phase(sample_count), status=Status.UNAVAILABLE, reason_code=code)
    samples = np.zeros(sample_count, dtype=np.float64)
    inventory = _inventory((), sample_count)
    result = compute_f14_cross_channel_event_association(
        phase=phase,
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=inventory,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=inventory,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("phase_reference_unavailable",)


def test_fewer_than_twenty_triggers_is_unavailable_with_empty_outputs() -> None:
    """Девятнадцать полных триггеров не достигают locked minimum и не дают нули."""
    sample_count = 6_400
    samples = np.zeros(sample_count, dtype=np.float64)
    events = tuple(_event(40 + index * 100, index + 1) for index in range(19))
    inventory = _inventory(events, sample_count)
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=inventory,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=inventory,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("insufficient_triggers",)
    assert result.relative_time_s.size == 0
    assert all(direction.qualified_trigger_count == 19 for direction in result.directions)
    assert all(direction.mean_waveform_v.size == 0 for direction in result.directions)


def test_boundary_trigger_is_counted_and_excluded_without_padding() -> None:
    """Граничный event не получает искусственные нулевые края окна."""
    sample_count = 6_400
    samples = np.zeros(sample_count, dtype=np.float64)
    valid = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    edge = _event(10, 21, boundary=True)
    inventory = _inventory((edge, *valid), sample_count)
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=inventory,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=inventory,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("window_truncated",)
    assert result.directions[0].boundary_trigger_count == 1
    assert result.directions[0].qualified_trigger_count == 20
    assert result.directions[0].stored_trigger_count == 20
    assert np.all(np.isfinite(result.directions[0].mean_waveform_v))


def test_event_cap_limits_stored_triggers_and_marks_partial() -> None:
    """Кап ограничивает count, но не подменяет минимум и не меняет ось."""
    sample_count = 6_400
    samples = np.zeros(sample_count, dtype=np.float64)
    events = tuple(_event(40 + index * 100, index + 1) for index in range(3))
    inventory = _inventory(events, sample_count)
    declarations = replace(
        F14Declarations.locked(),
        cycle_shift_offsets=(1, 2),
        minimum_triggers=1,
        maximum_triggers_per_direction=2,
    )
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=inventory,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=inventory,
        declarations=declarations,
        resources=_resources(),
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("event_limit",)
    assert result.directions[0].stored_trigger_count == 2
    assert result.directions[0].omitted_trigger_count == 1
    assert result.directions[0].baseline_probability.shape == (2, 401)


def test_nearest_lag_tie_breaks_to_earlier_target_event() -> None:
    """Равные модули лага выбирают более ранний target, а не порядок ответа."""
    sample_count = 6_400
    ch1_samples = np.zeros(sample_count, dtype=np.float64)
    ch2_samples = np.zeros(sample_count, dtype=np.float64)
    ch1_events = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    ch2_events: list[RootEvent] = []
    for index in range(20):
        centre = 40 + index * 100
        ch2_events.extend((_event(centre - 4, 2 * index + 1), _event(centre + 4, 2 * index + 2)))
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=ch1_samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=_inventory(ch1_events, sample_count),
        ch2_samples=ch2_samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=_inventory(tuple(ch2_events), sample_count),
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.directions[0].nearest_lag_s == pytest.approx(np.full(20, -0.004))
    reverse_lags = result.directions[1].nearest_lag_s
    assert reverse_lags == pytest.approx(np.asarray([0.004, -0.004] * 20))


def test_event_probability_uses_full_event_span_not_only_peak() -> None:
    """Occupancy отмечает весь [start,end] target event, а не только peak_sample."""
    sample_count = 6_400
    ch1_samples = np.zeros(sample_count, dtype=np.float64)
    ch2_samples = np.zeros(sample_count, dtype=np.float64)
    ch1_events = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    narrow = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    wide = tuple(
        replace(event, start_sample=event.peak_sample - 3, end_sample=event.peak_sample + 3)
        for event in narrow
    )
    narrow_result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=ch1_samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=_inventory(ch1_events, sample_count),
        ch2_samples=ch2_samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=_inventory(narrow, sample_count),
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )
    wide_result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=ch1_samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=_inventory(ch1_events, sample_count),
        ch2_samples=ch2_samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=_inventory(wide, sample_count),
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert narrow_result.status is Status.AVAILABLE
    assert wide_result.status is Status.AVAILABLE
    assert (
        wide_result.directions[0].event_probability.sum()
        > narrow_result.directions[0].event_probability.sum()
    )


def test_gap_crossing_trigger_is_counted_and_support_remains_partial() -> None:
    """Gap вырезает только пересекающие окна, а не весь доступный record support."""
    sample_count = 6_400
    samples = np.zeros(sample_count, dtype=np.float64)
    events = tuple(_event(40 + index * 100, index + 1) for index in range(21))
    gap = UnqualifiedGap(start_sample=35, end_sample=45, start_time_s=0.035, end_time_s=0.045)
    inventory = _inventory(events, sample_count, gaps=(gap,))
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=inventory,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=inventory,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("gaps_present",)
    assert result.directions[0].gap_crossing_trigger_count == 1
    assert result.directions[0].stored_trigger_count == 20
    assert result.directions[0].event_probability.size == 401


def test_engine_uses_full_replay_instead_of_truncated_stored_prefix() -> None:
    """Даже пустой persisted prefix не превращает полный replay в ноль триггеров."""
    sample_count = 6_400
    samples = np.zeros(sample_count, dtype=np.float64)
    events = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    full_inventory = _inventory(events, sample_count)
    truncated_prefix = replace(full_inventory, events=())
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=truncated_prefix,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=truncated_prefix,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.directions[0].qualified_trigger_count == 20
    assert result.directions[1].qualified_trigger_count == 20


def test_independent_cycle_events_stay_inside_cycle_shift_baseline() -> None:
    """Uniform-cycle independent events не создают observed peak вне baseline range."""
    sample_count = 6_400
    samples = np.zeros(sample_count, dtype=np.float64)
    ch1_events = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    ch2_events = tuple(_event(70 + index * 100, index + 1) for index in range(20))
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=_inventory(ch1_events, sample_count),
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=_inventory(ch2_events, sample_count),
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.AVAILABLE
    for direction in result.directions:
        assert np.all(direction.event_probability >= direction.baseline_low - 1e-12)
        assert np.all(direction.event_probability <= direction.baseline_high + 1e-12)
        assert direction.event_probability.max() == 0.0


def test_f14_declarations_reject_alternate_locked_vocabulary() -> None:
    """Tie-break и boundary handling нельзя подменить похожими строками."""
    with pytest.raises(ValueError, match="locked vocabulary"):
        replace(F14Declarations.locked(), nearest_event_tie_break="later_target")
    with pytest.raises(ValueError, match="locked vocabulary"):
        replace(F14Declarations.locked(), boundary_handling="pad_windows")


def test_f14_result_rejects_codes_outside_sorted_declared_vocabulary() -> None:
    """Публикуемая запись не принимает неизвестные или неупорядоченные причины."""
    result = compute_f14_cross_channel_event_association(
        phase=None,
        ch1_samples=None,
        ch1_phase_means=None,
        ch1_events=None,
        ch2_samples=None,
        ch2_phase_means=None,
        ch2_events=None,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )
    with pytest.raises(CharacterizationError):
        replace(result, reason_codes=("invented",))
    with pytest.raises(CharacterizationError):
        replace(result, reason_codes=(WINDOW_TRUNCATED, GAPS_PRESENT))
    assert result.reason_codes == (CHANNEL_MISSING,)
    assert DECLARED_CODES == (
        CHANNEL_MISSING,
        "channels_not_synchronous",
        "phase_reference_unavailable",
        "insufficient_triggers",
        WINDOW_TRUNCATED,
        GAPS_PRESENT,
        "event_limit",
    )


def test_partial_phase_support_reports_gaps_without_leaking_root_code() -> None:
    """Partial CH2 phase остаётся измеримымsupport, но не теряет QC code."""
    sample_count = 6_400
    phase = _phase(sample_count)
    phase = replace(
        phase,
        cycle_valid=np.concatenate((np.ones(20, dtype=np.bool_), np.zeros(44, dtype=np.bool_))),
        status=Status.PARTIAL,
        reason_code="grid_unstable",
    )
    samples = np.zeros(sample_count, dtype=np.float64)
    events = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    inventory = _inventory(events, sample_count)
    result = compute_f14_cross_channel_event_association(
        phase=phase,
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=inventory,
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=inventory,
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (GAPS_PRESENT,)
    assert result.qualified_cycle_count == 20


def test_nearest_lag_outside_window_is_omitted_not_zero_filled() -> None:
    """Событие вне declared lag range не превращается в искусственный нулевой lag."""
    sample_count = 6_400
    samples = np.zeros(sample_count, dtype=np.float64)
    ch1_events = tuple(_event(40 + index * 100, index + 1) for index in range(20))
    ch2_events = tuple(_event(70 + index * 100, index + 1) for index in range(20))
    result = compute_f14_cross_channel_event_association(
        phase=_phase(sample_count),
        ch1_samples=samples,
        ch1_phase_means=_means(sample_count),
        ch1_events=_inventory(ch1_events, sample_count),
        ch2_samples=samples,
        ch2_phase_means=_means(sample_count),
        ch2_events=_inventory(ch2_events, sample_count),
        declarations=F14Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.directions[0].nearest_lag_s.size == 0
    assert result.directions[1].nearest_lag_s.size == 0
