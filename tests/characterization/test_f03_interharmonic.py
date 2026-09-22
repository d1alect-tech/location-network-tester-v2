"""F03 synchronous_bin_nearest_neighbor_tracks RED analytic tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.f01_phase_cycle import F01Result
from lnt.characterization.f03_interharmonic import (
    METHOD,
    F03Result,
    compute_f03_interharmonic_tracks,
)
from lnt.characterization.records import Status

FS_HZ = 50_000.0
F1_HZ = 50.0
WINDOW_S = 0.2
BIN_SPACING_HZ = 5.0
ASSOCIATION_TOLERANCE_BINS = 2
DETECTION_MARGIN_DB = 6.0
LOCAL_MEDIAN_BIN_COUNT = 11
MINIMUM_LIFETIME_WINDOWS = 3
SUBHARMONIC_ORDERS = (2, 3, 4)
MAXIMUM_TRACKS = 4096
WINDOWS = 12
DECLARED_CODES = frozenset(
    {
        "below_resolution",
        "peak_not_observed",
        "track_too_short",
        "leakage_ambiguous",
        "grid_unstable",
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
    window_s: float = WINDOW_S
    bin_spacing_hz: float = BIN_SPACING_HZ
    association_tolerance_bins: int = ASSOCIATION_TOLERANCE_BINS
    detection_margin_db: float = DETECTION_MARGIN_DB
    local_median_bin_count: int = LOCAL_MEDIAN_BIN_COUNT
    minimum_lifetime_windows: int = MINIMUM_LIFETIME_WINDOWS
    subharmonic_orders: tuple[int, ...] = SUBHARMONIC_ORDERS
    maximum_tracks: int = MAXIMUM_TRACKS
    resources: ResourceLimits = field(default_factory=_resources)


def _f01(f1_hz: float | None) -> F01Result:
    if f1_hz is None:
        return F01Result(
            status=Status.UNAVAILABLE,
            reason_codes=("grid_unstable",),
            f1_hz=None,
            c_k_v=None,
            phi_rel_k_rad=None,
            phase_resultant_k=None,
            x_template_v=None,
            window_count=WINDOWS,
            evaluated_window_count=0,
        )
    return F01Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        f1_hz=float(f1_hz),
        c_k_v=None,
        phi_rel_k_rad=None,
        phase_resultant_k=None,
        x_template_v=None,
        window_count=WINDOWS,
        evaluated_window_count=WINDOWS,
    )


def _evaluate(samples: np.ndarray, f01: F01Result | None = None, **overrides: object) -> F03Result:
    declared = replace(_Declared(), **overrides)
    grid = _f01(F1_HZ) if f01 is None else f01
    return compute_f03_interharmonic_tracks(
        samples,
        sample_rate_hz=declared.sample_rate_hz,
        f01_result=grid,
        window_s=declared.window_s,
        bin_spacing_hz=declared.bin_spacing_hz,
        association_tolerance_bins=declared.association_tolerance_bins,
        detection_margin_db=declared.detection_margin_db,
        local_median_bin_count=declared.local_median_bin_count,
        minimum_lifetime_windows=declared.minimum_lifetime_windows,
        subharmonic_orders=declared.subharmonic_orders,
        maximum_tracks=declared.maximum_tracks,
        resources=declared.resources,
    )


def _times(sample_count: int) -> np.ndarray:
    return np.arange(sample_count, dtype=np.float64) / FS_HZ


def _harmonic_only(sample_count: int) -> np.ndarray:
    t = _times(sample_count)
    return (
        6.0 * np.sin(2.0 * np.pi * F1_HZ * t)
        + 0.6 * np.sin(2.0 * np.pi * 3.0 * F1_HZ * t)
        + 0.3 * np.sin(2.0 * np.pi * 5.0 * F1_HZ * t)
    )


def _with_tone(sample_count: int, freq_hz: float, peak_v: float) -> np.ndarray:
    t = _times(sample_count)
    return _harmonic_only(sample_count) + peak_v * np.sin(2.0 * np.pi * freq_hz * t)


def test_method_is_the_declared_recipe_method() -> None:
    assert METHOD == "synchronous_bin_nearest_neighbor_tracks"


def test_positive_tone_tracked_in_correct_bin_with_full_lifetime() -> None:
    """Допуск частоты — половина объявленного бина: центроид он-грид тона.

    Замер конвейера (probe sync_grid + rms_power_spectrum): синхронная сетка
    ставит (h+0.5)*f1 ровно в бин k=25, соседи k=24/26 на уровне 1e-15,
    энергоцентроид равен 125.0 Гц с дрожанием 3e-14 (квант бина f1/10 = 5 Гц).
    Амплитуда — RMS-конвенция detector.py:99-105 (A/sqrt(2) = 0.3536 В);
    замер дал точное совпадение, допуск 5 % — запас на дробный f1.
    Ширина однобинового пика упирается в пол разрешения 1/window_s = 5 Гц.
    """
    n = int(WINDOWS * WINDOW_S * FS_HZ)
    result = _evaluate(_with_tone(n, 2.5 * F1_HZ, 0.5))
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.f_hz.size == 1
    assert abs(float(result.f_hz[0]) - 2.5 * F1_HZ) <= BIN_SPACING_HZ / 2.0
    assert float(result.a_v[0]) == pytest.approx(0.5 / np.sqrt(2.0), rel=0.05)
    assert float(result.df_hz[0]) >= 1.0 / WINDOW_S - 1e-9
    assert float(result.t_life_s[0]) == pytest.approx(WINDOWS * WINDOW_S)
    assert int(result.windows_observed[0]) == WINDOWS
    assert set(result.reason_codes) <= DECLARED_CODES


def test_control_harmonic_only_yields_no_sustained_track() -> None:
    """Чистые гармоники он-грид: IHG-бины несут только численный шум."""
    n = int(WINDOWS * WINDOW_S * FS_HZ)
    result = _evaluate(_harmonic_only(n))
    assert result.status is Status.UNAVAILABLE
    assert result.f_hz.size == 0
    assert "peak_not_observed" in result.reason_codes
    assert set(result.reason_codes) <= DECLARED_CODES


def test_control_single_window_detection_does_not_form_track() -> None:
    """Одиночный оконный детект короче minimum_lifetime_windows треком не становится."""
    n = int(WINDOWS * WINDOW_S * FS_HZ)
    samples = _harmonic_only(n)
    win = int(WINDOW_S * FS_HZ)
    samples[:win] = _with_tone(win, 2.5 * F1_HZ, 0.5)[:win]
    result = _evaluate(samples)
    assert result.status is Status.UNAVAILABLE
    assert result.f_hz.size == 0
    assert "track_too_short" in result.reason_codes
    assert set(result.reason_codes) <= DECLARED_CODES


def test_limitation_near_harmonic_trips_below_resolution() -> None:
    """Тон в одном измеренном бине от гармоники — неразрешённая линия.

    Тон на 55 Гц сидит в гард-бине k=11 (f1 + один бин 5 Гц): ближайший
    гармонический бин k=10 на расстоянии ровно одного измеренного бина
    f1/10, поэтому линия уходит в below_resolution, а не публикуется.
    """
    n = int(WINDOWS * WINDOW_S * FS_HZ)
    result = _evaluate(_with_tone(n, F1_HZ + BIN_SPACING_HZ, 0.5))
    assert result.status is Status.UNAVAILABLE
    assert result.f_hz.size == 0
    assert "below_resolution" in result.reason_codes
    assert set(result.reason_codes) <= DECLARED_CODES


def test_gap_breaks_track_without_interpolation() -> None:
    """Окно без линии рвёт трек: gap_interpolation="none" залочено контрактом."""
    windows = 6
    n = int(windows * WINDOW_S * FS_HZ)
    win = int(WINDOW_S * FS_HZ)
    samples = _with_tone(n, 2.5 * F1_HZ, 0.5)
    samples[2 * win : 3 * win] = _harmonic_only(win)
    result = _evaluate(samples, minimum_lifetime_windows=2)
    assert result.f_hz.size == 2
    assert int(np.sum(result.windows_missing)) >= 1
    assert bool(np.all(result.windows_observed >= 2))
    assert "peak_not_observed" in result.reason_codes
    assert set(result.reason_codes) <= DECLARED_CODES


def test_cap_is_deterministic_with_omitted_count() -> None:
    """Превышение maximum_tracks: дольше живущие, тай-брейк по меньшему центру."""
    n = int(WINDOWS * WINDOW_S * FS_HZ)
    samples = _with_tone(n, 2.5 * F1_HZ, 0.5)
    samples = samples + 0.5 * np.sin(2.0 * np.pi * 3.5 * F1_HZ * _times(n))
    samples = samples + 0.5 * np.sin(2.0 * np.pi * 4.5 * F1_HZ * _times(n))
    first = _evaluate(samples, maximum_tracks=2)
    second = _evaluate(samples, maximum_tracks=2)
    assert first.f_hz.size == 2
    assert np.array_equal(first.f_hz, second.f_hz)
    assert np.array_equal(first.f_hz, np.sort(first.f_hz))
    assert first.omitted_track_count == first.candidate_track_count - 2
    assert first.omitted_track_count >= 1
    assert set(first.reason_codes) <= DECLARED_CODES


def test_grid_unstable_when_f01_has_no_f1() -> None:
    """Без сетки F01 собственной оценки нет: UNAVAILABLE grid_unstable."""
    n = int(WINDOWS * WINDOW_S * FS_HZ)
    result = _evaluate(_with_tone(n, 2.5 * F1_HZ, 0.5), f01=_f01(None))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("grid_unstable",)
    assert result.f_hz.size == 0
    assert result.a_v.size == 0
