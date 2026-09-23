"""F10 phase_residual_threshold_duration_v2s_surface RED analytic tests (todo 19)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization import f10_threshold_surface as engine
from lnt.characterization.clipping import ClippingBounds
from lnt.characterization.f10_result import (
    ARTIFACT_LIMIT,
    CLAIM_BOUNDARY,
    CLIPPED,
    DECLARED_CODES,
    DURATION_BELOW_SAMPLE_RESOLUTION,
    INSUFFICIENT_PHASE_SUPPORT,
    MAD_FACTOR,
    MAD_SCALE,
    METHOD,
    MINIMUM_SAMPLES_AT_SHORTEST_DURATION,
    MINIMUM_SAMPLES_PER_BIN,
    OCCUPANCY_ONLY_TRUNCATED,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
    F10Result,
)
from lnt.characterization.f10_threshold_surface import compute_f10_threshold_surface
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status, Unit, validate_unit_name

if TYPE_CHECKING:
    from collections.abc import Sequence

FS_HZ = 100_000.0
BINS = 64
CYCLE_SAMPLES = 64
CYCLES = 32
# Фоновая величина u даёт положительный MAD ровно u/2 (половина отсчётов нулевая,
# половина u), поэтому порог 3·1.4826·MAD ≈ 2.22·u стоит НАД максимумом фона и
# НИЖЕ импульса A — occupancy точна аналитически, а не подогнана по движку.
BACKGROUND_V = 1.0 / 1024.0
PULSE_V = 5.0
PULSE_SAMPLES = 4
PULSE_START_BIN = 8
# Импульс стоит ровно в двух циклах противоположных знаков: иначе фазовое среднее
# его бы ПОГЛОТИЛО, а F10 ищет именно не фазо-запертые выбросы. Так сумма каждого
# бина ровно ноль, и остаток совпадает с сигналом.
PULSED_CYCLES = 2
SIGMAS = (3.0, 5.0, 8.0, 12.0)
DURATIONS = (0.0, 0.00002, 0.0001, 0.001, 0.01)
QUANTILES = (0.5, 0.9, 0.99)
PULSE_DURATION_S = PULSE_SAMPLES / FS_HZ
PULSE_V2_S = PULSE_V**2 * PULSE_DURATION_S
_NOISE_CYCLES = 2000
_TWO_SIDED_P = 0.0026997960632601866
EXPECTED_CODES = frozenset(
    {
        "phase_reference_unavailable",
        "insufficient_phase_support",
        "scale_zero",
        "duration_below_sample_resolution",
        "clipped",
        "artifact_limit",
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

    sample_rate_hz: float = FS_HZ
    phase_bins: int = BINS
    scale: str = MAD_SCALE
    threshold_sigma: tuple[float, ...] = SIGMAS
    minimum_duration_s: tuple[float, ...] = DURATIONS
    quantiles: tuple[float, ...] = QUANTILES
    edge_episode_handling: str = OCCUPANCY_ONLY_TRUNCATED
    maximum_episodes: int = 4096
    clipping: ClippingBounds | None = None
    gap_mask: np.ndarray | None = None
    resources: ResourceLimits = field(default_factory=_resources)


def _phase(cycles: int, *, rate: float = FS_HZ, status: Status = Status.AVAILABLE) -> PhaseCycles:
    starts = np.arange(cycles, dtype=np.float64) * CYCLE_SAMPLES
    return PhaseCycles(
        sample_rate_hz=rate,
        sample_count=cycles * CYCLE_SAMPLES,
        cycle_start_samples=starts,
        cycle_end_samples=starts + CYCLE_SAMPLES,
        cycle_valid=np.ones(cycles, dtype=np.bool_),
        status=status,
        reason_code=None,
    )


def _means(bins: int = BINS, *, support: int = CYCLES) -> PhaseMeans:
    """Нулевое фазовое среднее: истинное среднее каждого бина фикстуры равно нулю."""
    return PhaseMeans(
        means_v=np.zeros(bins, dtype=np.float64),
        counts=np.full(bins, support, dtype=np.int64),
        valid_bins=np.ones(bins, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _pulse_signal(
    cycles: int,
    *,
    start_bin: int = PULSE_START_BIN,
    width: int = PULSE_SAMPLES,
) -> np.ndarray:
    """Импульсы ±A на фоне с рызбросом величины и нулевым средним по каждому бину.

    Фон строится парами циклов на каждом смещении ``j``: чётный цикл даёт
    ``+u`` при чётном ``j`` и ``0`` при нечётном, следующий за ним — ``-u`` при
    чётном ``j`` и ``0`` при нечётном. Отсюда ``sum = 0`` по каждому бину (значит
    остаток равен сигналу, а фазовое среднее не влияет), величины ``|r|`` равны
    ``u`` ровно у половины отсчётов и нулю у половины (значит MAD = u/2 > 0).
    Импульсы стоят в первых двух циклах с противоположными знаками, поэтому и
    они дают по каждому своему бину ровно ноль.
    """
    signal = np.zeros(cycles * CYCLE_SAMPLES, dtype=np.float64)
    for index in range(cycles):
        base = index * CYCLE_SAMPLES
        sign = 1.0 if index % 2 == 0 else -1.0
        offsets = np.arange(CYCLE_SAMPLES)
        signal[base : base + CYCLE_SAMPLES] = np.where(offsets % 2 == 0, sign * BACKGROUND_V, 0.0)
        if index < PULSED_CYCLES:
            signal[base + start_bin : base + start_bin + width] = sign * PULSE_V
    return signal


def _run(
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    declared: _Declared | None = None,
) -> F10Result:
    d = declared or _Declared()
    return compute_f10_threshold_surface(
        samples,
        phase,
        means,
        sample_rate_hz=d.sample_rate_hz,
        phase_bins=d.phase_bins,
        scale=d.scale,
        threshold_sigma=d.threshold_sigma,
        minimum_duration_s=d.minimum_duration_s,
        quantiles=d.quantiles,
        edge_episode_handling=d.edge_episode_handling,
        maximum_episodes=d.maximum_episodes,
        resources=d.resources,
        clipping=d.clipping,
        gap_mask=d.gap_mask,
    )


def _cells(result: F10Result) -> tuple[np.ndarray, ...]:
    """Все ячейки поверхности: они обязаны делить одну объявленную форму."""
    return (
        result.occupancy,
        result.episode_count,
        result.total_v2_s,
        result.retained_samples,
        result.truncated_samples,
    )


def test_locked_parameters_match_the_frozen_contract() -> None:
    """Метод и залоченные значения рецепта characterization-v1."""
    assert METHOD == "phase_residual_threshold_duration_v2s_surface"
    assert MAD_SCALE == "mad_times_1.4826"
    assert MAD_FACTOR == 1.4826
    assert OCCUPANCY_ONLY_TRUNCATED == "occupancy_only_truncated"
    assert MINIMUM_SAMPLES_PER_BIN == 20
    assert MINIMUM_SAMPLES_AT_SHORTEST_DURATION == 2


def test_reason_code_vocabulary_is_closed() -> None:
    """Объявленный словарь кодов закрыт и публичен, без посторонних значений."""
    assert DECLARED_CODES == (
        PHASE_REFERENCE_UNAVAILABLE,
        INSUFFICIENT_PHASE_SUPPORT,
        SCALE_ZERO,
        DURATION_BELOW_SAMPLE_RESOLUTION,
        CLIPPED,
        ARTIFACT_LIMIT,
    )
    assert set(DECLARED_CODES) == EXPECTED_CODES


def test_claim_boundary_is_published() -> None:
    """Граница притязаний спеки: одна измеренная плоскость, не энергия и не источник."""
    assert "one measured channel plane" in CLAIM_BOUNDARY
    for forbidden in ("energy", "damage", "source identity", "utility"):
        assert forbidden in CLAIM_BOUNDARY
    assert "does not measure" in CLAIM_BOUNDARY


def test_rectangular_pulses_give_exact_occupancy_duration_count_and_v2s() -> None:
    """Положительное из спеки: A²T на сетке отсчётов, occupancy и счётчик точны."""
    result = _run(_pulse_signal(CYCLES), _phase(CYCLES), _means())
    pulsed = slice(PULSE_START_BIN, PULSE_START_BIN + PULSE_SAMPLES)
    start = PULSE_START_BIN
    share = PULSED_CYCLES / CYCLES

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert _cells(result)[0].shape == (len(SIGMAS), len(DURATIONS), BINS)
    assert result.qualified_cycles == CYCLES
    assert np.all(result.qualified_samples == CYCLES)
    # occupancy по-отсчётная: импульсные отсчёты удержаны, фон не перешёл порог.
    assert np.all(result.occupancy[:, 0, pulsed] == pytest.approx(share, rel=1e-12))
    assert np.all(result.occupancy[:, 0, :PULSE_START_BIN] == 0.0)
    assert np.all(result.occupancy[:, 0, PULSE_START_BIN + PULSE_SAMPLES :] == 0.0)
    assert np.all(result.retained_samples[:, 0, pulsed] == PULSED_CYCLES)
    # Эпизодные величины объектные и адресуются бином начала (F10-8).
    assert np.all(result.episode_count[:, 0, start] == PULSED_CYCLES)
    assert np.all(result.episode_count[:, 0, start + 1 :] == 0)
    assert np.all(
        result.total_v2_s[:, 0, start] == pytest.approx(PULSED_CYCLES * PULSE_V2_S, rel=1e-12)
    )
    assert np.all(result.total_v2_s[:, 0, start + 1 :] == 0.0)
    # Квантили длительности и V²s вырождены на прямоугольной истине.
    assert np.all(
        result.duration_quantile_s[:, 0, start, :] == pytest.approx(PULSE_DURATION_S, rel=1e-12)
    )
    assert np.all(
        result.episode_quantile_v2_s[:, 0, start, :] == pytest.approx(PULSE_V2_S, rel=1e-12)
    )
    assert np.all(result.quantile_valid[:, 0, start])
    assert np.all(~result.quantile_valid[:, 0, start + 1 :])
    assert (result.sample_count, result.observation_count) == (
        CYCLES * CYCLE_SAMPLES,
        CYCLES * BINS,
    )
    assert result.missing_count == 0
    assert result.episode_total == len(SIGMAS) * PULSED_CYCLES
    assert result.truncated_episode_total == 0
    assert result.stored_count == len(SIGMAS) * PULSED_CYCLES
    assert result.omitted_count == 0
    first = result.episodes[0]
    assert (first.sigma, first.phase_bin) == (SIGMAS[0], start)
    assert first.start_time_s == pytest.approx(PULSE_START_BIN / FS_HZ, rel=1e-12)
    assert first.duration_s == pytest.approx(PULSE_DURATION_S, rel=1e-12)
    assert first.v2_s == pytest.approx(PULSE_V2_S, rel=1e-12)


def test_duration_cells_above_the_run_width_are_empty() -> None:
    """Ограничение: 4 отсчёта проходят ячейки 0 и 2·10⁻⁵ с и не проходят 10⁻⁴ с."""
    result = _run(_pulse_signal(CYCLES), _phase(CYCLES), _means())
    start = PULSE_START_BIN

    assert np.all(result.episode_count[:, 1, start] == PULSED_CYCLES)
    assert np.all(result.occupancy[:, 1, slice(start, start + PULSE_SAMPLES)] > 0.0)
    for cell in (2, 3, 4):
        assert np.all(result.episode_count[:, cell, :] == 0)
        assert np.all(result.occupancy[:, cell, :] == 0.0)
        assert np.all(result.total_v2_s[:, cell, :] == 0.0)
        assert np.all(~result.quantile_valid[:, cell, :])


def test_one_sample_pulse_is_absent_at_a_two_sample_minimum() -> None:
    """Ограничение из спеки: односэмпловый импульс отсутствует в ячейке 2 отсчётов."""
    result = _run(_pulse_signal(CYCLES, width=1), _phase(CYCLES), _means())
    bin_at = PULSE_START_BIN

    assert result.status is Status.AVAILABLE
    assert DURATION_BELOW_SAMPLE_RESOLUTION not in result.reason_codes
    assert np.all(result.episode_count[:, 0, bin_at] == PULSED_CYCLES)
    assert np.all(result.episode_count[:, 1, bin_at] == 0)
    assert np.all(result.occupancy[:, 0, bin_at] > 0.0)
    assert np.all(result.occupancy[:, 1, bin_at] == 0.0)


def test_boundary_pulse_keeps_occupancy_and_marks_truncated_support() -> None:
    """Граничный импульс: усечён, остаётся в occupancy, вне квантилей и хранения."""
    result = _run(_pulse_signal(CYCLES, start_bin=0), _phase(CYCLES), _means())
    pulsed = slice(0, PULSE_SAMPLES)
    share = PULSED_CYCLES / CYCLES

    assert result.status is Status.AVAILABLE
    # Оба импульса занимают одни и те же бины, значит occupancy видит оба,
    # а усечённая поддержка отмечает ровно один из них (касание начала записи).
    assert np.all(result.occupancy[:, 0, pulsed] == pytest.approx(share, rel=1e-12))
    assert np.all(result.truncated_samples[:, 0, pulsed] == 1)
    assert np.all(result.episode_count[:, 0, 0] == 1)
    assert np.all(result.episode_count[:, 0, 1:] == 0)
    assert result.truncated_episode_total == len(SIGMAS)
    assert result.episode_total == len(SIGMAS)
    assert result.stored_count == len(SIGMAS)
    assert np.all(result.quantile_valid[:, 0, 0])
    assert np.all(
        result.duration_quantile_s[:, 0, 0, :] == pytest.approx(PULSE_DURATION_S, rel=1e-12)
    )


def test_gap_mask_excludes_samples_and_truncates_neighbours() -> None:
    """Объявленная маска пропусков: исключает отсчёты и делает соседний прогон усечённым."""
    samples = _pulse_signal(CYCLES)
    mask = np.zeros(samples.size, dtype=np.bool_)
    # Пропуск садится ровно на первый отсчёт после импульса в каждом импульсном
    # цикле: прогон остаётся целым по длине, но правый сосед не квалифицирован,
    # значит он усечён и виден только в occupancy и усечённой поддержке.
    for index in range(PULSED_CYCLES):
        mask[index * CYCLE_SAMPLES + PULSE_START_BIN + PULSE_SAMPLES] = True
    result = _run(samples, _phase(CYCLES), _means(), replace(_Declared(), gap_mask=mask))
    start = PULSE_START_BIN

    assert result.status is Status.AVAILABLE
    assert result.observation_count == samples.size - PULSED_CYCLES
    assert result.missing_count == PULSED_CYCLES
    # Оба импульсных цикла дают усечённый прогон; счётчики и квантили пусты.
    assert np.all(result.truncated_samples[:, 1, start] == PULSED_CYCLES)
    assert np.all(result.retained_samples[:, 1, start] == 0)
    assert result.episode_total == 0
    assert result.truncated_episode_total == len(SIGMAS) * PULSED_CYCLES
    assert np.all(~result.quantile_valid[:, 1, start])
    # Знаменатель occupancy — квалифицированные отсчёты того же бина (по одному
    # в каждом цикле), числитель — оба импульсных отсчёта.
    assert np.all(
        result.occupancy[:, 1, start : start + PULSE_SAMPLES]
        == pytest.approx(PULSED_CYCLES / CYCLES, rel=1e-12)
    )


def test_phase_independent_noise_has_no_phase_cell_bias() -> None:
    """Контроль: фазо-независимый шум не даёт систематической разницы по бинам."""
    rng = np.random.default_rng(6022)
    result = _run(
        rng.standard_normal(_NOISE_CYCLES * CYCLE_SAMPLES),
        _phase(_NOISE_CYCLES),
        _means(support=_NOISE_CYCLES),
    )
    occupancy = np.asarray(result.occupancy[0, 0, :], dtype=np.float64)
    per_bin = math.sqrt(_TWO_SIDED_P * (1.0 - _TWO_SIDED_P) / _NOISE_CYCLES)
    mean_sd = per_bin / math.sqrt(BINS)

    assert result.status is Status.AVAILABLE
    assert np.count_nonzero(occupancy) >= 20
    assert float(np.max(np.abs(occupancy - _TWO_SIDED_P))) <= 5.0 * per_bin
    assert abs(float(np.mean(occupancy)) - _TWO_SIDED_P) <= 4.0 * mean_sd


def test_zero_scale_refuses_with_declared_code() -> None:
    """Нулевой MAD: масштаб не определён, поверхность не публикуется."""
    result = _run(np.zeros(CYCLES * CYCLE_SAMPLES), _phase(CYCLES), _means())

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (SCALE_ZERO,)
    assert result.occupancy.size == 0
    assert result.episodes == ()
    # Поддержка честная: отказ случился на масштабе, а не на квалификации.
    assert result.observation_count == CYCLES * BINS
    assert np.all(result.qualified_samples == CYCLES)


def test_unavailable_phase_root_maps_to_phase_reference_unavailable() -> None:
    """Отказ корня фазы сворачивается в объявленный код семейства."""
    result = _run(
        _pulse_signal(CYCLES),
        _phase(0, status=Status.UNAVAILABLE),
        _means(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert result.occupancy.size == 0
    assert result.qualified_samples.shape == (0,)
    assert result.stored_count == 0


def test_underfilled_phase_bins_refuse_with_declared_code() -> None:
    """Меньше 20 квалифицированных отсчётов в бине: поддержка поверхности недостаточна."""
    result = _run(_pulse_signal(1), _phase(1), _means(support=1))

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (INSUFFICIENT_PHASE_SUPPORT,)
    assert np.all(result.qualified_samples == 1)
    assert result.occupancy.size == 0


def test_duration_below_sample_resolution_refuses_with_declared_code() -> None:
    """Кратчайшая ненулевая ячейка короче двух отсчётов: поверхность не считается."""
    declared = replace(_Declared(), sample_rate_hz=8000.0)
    result = _run(_pulse_signal(CYCLES), _phase(CYCLES, rate=8000.0), _means(), declared)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (DURATION_BELOW_SAMPLE_RESOLUTION,)
    assert result.occupancy.size == 0


def test_clipped_intervals_are_excluded_with_declared_code() -> None:
    """Клиппированный интервал исключён из квалификации и объявлен кодом."""
    cycles = 128
    bounds = ClippingBounds(low_v=-1.0, high_v=6.0, reason_code=None, telemetry_rail_count=None)
    declared = replace(_Declared(), clipping=bounds, maximum_episodes=4096)
    result = _run(_pulse_signal(cycles), _phase(cycles), _means(support=cycles), declared)
    pulsed = slice(PULSE_START_BIN, PULSE_START_BIN + PULSE_SAMPLES)

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (CLIPPED,)
    # Импульсы −A второго цикла стоят на нижней рельсе и исключены целиком;
    # положительный импульс остаётся, поэтому occupancy = 1 из cycles − 1
    # квалифицированных отсчётов этого бина.
    assert np.all(result.qualified_samples[pulsed] == cycles - 1)
    assert result.qualified_samples[0] == cycles
    assert result.observation_count == cycles * CYCLE_SAMPLES - PULSE_SAMPLES
    assert result.missing_count == PULSE_SAMPLES
    assert np.all(result.occupancy[:, 0, pulsed] == pytest.approx(1.0 / (cycles - 1), rel=1e-12))
    assert np.all(result.episode_count[:, 0, PULSE_START_BIN] == 1)


def test_episode_storage_limit_is_declared_and_deterministic() -> None:
    """Лимит хранения: сводки полные, хранение усечено префиксом, код объявлен."""
    declared = replace(_Declared(), maximum_episodes=3)
    result = _run(_pulse_signal(CYCLES), _phase(CYCLES), _means(), declared)
    start = PULSE_START_BIN
    total = len(SIGMAS) * PULSED_CYCLES

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (ARTIFACT_LIMIT,)
    # Сводки считаются по всем эпизодам, лимит хранения их не режет.
    assert np.all(result.episode_count[:, 0, start] == PULSED_CYCLES)
    assert result.episode_total == total
    assert result.stored_count == 3
    assert result.omitted_count == total - 3
    assert len(result.episodes) == 3
    assert [item.start_time_s for item in result.episodes] == pytest.approx(
        [
            PULSE_START_BIN / FS_HZ,
            (PULSE_START_BIN + CYCLE_SAMPLES) / FS_HZ,
            PULSE_START_BIN / FS_HZ,
        ],
        rel=1e-12,
    )
    assert [item.sigma for item in result.episodes] == pytest.approx(
        [SIGMAS[0], SIGMAS[0], SIGMAS[1]], rel=1e-12
    )


def test_member_limit_overflow_keeps_a_deterministic_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Предел буфера квантилей объявлен; квантили берутся с детерминированного префикса."""
    monkeypatch.setattr(engine, "_MEMBER_LIMIT", PULSED_CYCLES)
    result = _run(_pulse_signal(CYCLES), _phase(CYCLES), _means())
    start = PULSE_START_BIN

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (ARTIFACT_LIMIT,)
    assert result.stored_count == len(SIGMAS) * PULSED_CYCLES
    # Бюджет исчерпан первым порогом, поэтому квантиль определён только у него.
    assert np.all(result.quantile_valid[0, 0, start])
    assert np.all(~result.quantile_valid[1:, 0, start])
    assert np.all(
        result.episode_quantile_v2_s[0, 0, start, :] == pytest.approx(PULSE_V2_S, rel=1e-12)
    )


def test_runs_are_bitwise_deterministic() -> None:
    """Два прогона дают побитово идентичные ячейки, счётчики и хранимые эпизоды."""
    samples = _pulse_signal(CYCLES, start_bin=0)
    first = _run(samples, _phase(CYCLES), _means())
    second = _run(samples, _phase(CYCLES), _means())

    for left, right in zip(_cells(first), _cells(second), strict=True):
        assert np.array_equal(left, right)
    assert np.array_equal(first.duration_quantile_s, second.duration_quantile_s)
    assert np.array_equal(first.quantile_valid, second.quantile_valid)
    assert first.episodes == second.episodes
    assert (first.stored_count, first.omitted_count) == (
        second.stored_count,
        second.omitted_count,
    )


def test_declared_smaller_resource_budget_does_not_change_the_surface() -> None:
    """resources принимается и не тратится: бюджет не режет и не меняет результат."""
    samples = _pulse_signal(CYCLES)
    default = _run(samples, _phase(CYCLES), _means())
    tiny = replace(
        _Declared(),
        resources=ResourceLimits(
            chunk_samples=1024,
            hard_max_chunk_samples=1_048_576,
            max_work_bytes=65_536,
            max_artifact_bytes=1024,
            max_stored_trajectories=1,
            max_surrogates=1,
            deterministic_seed=6022,
        ),
    )
    small = _run(samples, _phase(CYCLES), _means(), tiny)

    for left, right in zip(_cells(default), _cells(small), strict=True):
        assert np.array_equal(left, right)
    assert default.status is small.status is Status.AVAILABLE
    assert default.reason_codes == small.reason_codes == ()


def test_mismatched_phase_mean_bin_count_raises_valueerror() -> None:
    """Число бинов остатка и поверхности должно совпадать, иначе ValueError."""
    with pytest.raises(ValueError, match="phase mean bin count"):
        _run(_pulse_signal(CYCLES), _phase(CYCLES), _means(bins=16))


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    [
        ("sample_rate_hz", float("nan"), "sample rate"),
        ("sample_rate_hz", float("inf"), "sample rate"),
        ("sample_rate_hz", 0.0, "sample rate"),
        ("sample_rate_hz", -FS_HZ, "sample rate"),
        ("phase_bins", 0, "phase_bins"),
        ("phase_bins", -64, "phase_bins"),
        ("scale", "std_zero_mean", "scale"),
        ("edge_episode_handling", "exclude_edges", "edge_episode_handling"),
        ("maximum_episodes", 0, "maximum_episodes"),
        ("threshold_sigma", (), "threshold_sigma"),
        ("threshold_sigma", (0.0,), "threshold_sigma"),
        ("threshold_sigma", (float("nan"),), "threshold_sigma"),
        ("threshold_sigma", (float("inf"),), "threshold_sigma"),
        ("minimum_duration_s", (), "minimum_duration_s"),
        ("minimum_duration_s", (-1e-6,), "minimum_duration_s"),
        ("minimum_duration_s", (float("nan"),), "minimum_duration_s"),
        ("quantiles", (), "quantiles"),
        ("quantiles", (0.0,), "quantiles"),
        ("quantiles", (1.0,), "quantiles"),
        ("quantiles", (float("nan"),), "quantiles"),
        ("gap_mask", np.zeros(5, dtype=np.bool_), "gap_mask"),
    ],
)
def test_invalid_numeric_inputs_raise_valueerror(
    field_name: str, value: object, match: str
) -> None:
    """Невалидные числа и необъявленные значения — ValueError, а не отказ словарём."""
    declared = replace(_Declared(), **{field_name: value})
    with pytest.raises(ValueError, match=match):
        _run(_pulse_signal(CYCLES), _phase(CYCLES), _means(), declared)


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("f10_occupancy", Unit.RATIO),
        ("f10_episode_count", Unit.COUNT),
        ("f10_support_samples", Unit.COUNT),
        ("f10_support_cycles", Unit.COUNT),
        ("f10_truncated_samples", Unit.COUNT),
        ("f10_threshold_sigma", Unit.RATIO),
        ("f10_quantiles", Unit.RATIO),
        ("f10_minimum_duration_s", Unit.S),
        ("f10_duration_q50_s", Unit.S),
        ("f10_total_v2_s", Unit.V2_S),
        ("f10_episode_q50_v2_s", Unit.V2_S),
    ],
)
def test_persisted_names_are_accepted_by_the_unit_vocabulary(name: str, unit: Unit) -> None:
    """Опубликованные величины подписаны членами закрытого словаря единиц."""
    validate_unit_name(name, unit)


def test_axis_arrays_carry_the_declared_surface_axes() -> None:
    """Раскладка поверхности: оси объявлены значениями, а не только индексами."""
    result = _run(_pulse_signal(CYCLES), _phase(CYCLES), _means())
    shape: Sequence[int] = result.occupancy.shape

    assert np.array_equal(result.threshold_sigma, np.asarray(SIGMAS, dtype=np.float64))
    assert np.array_equal(result.minimum_duration_s, np.asarray(DURATIONS, dtype=np.float64))
    assert np.array_equal(result.quantiles, np.asarray(QUANTILES, dtype=np.float64))
    assert tuple(shape) == (len(SIGMAS), len(DURATIONS), BINS)
    assert result.duration_quantile_s.shape == (*shape, len(QUANTILES))
    assert result.episode_quantile_v2_s.shape == (*shape, len(QUANTILES))
