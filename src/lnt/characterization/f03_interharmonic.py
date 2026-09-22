"""F03 synchronous_bin_nearest_neighbor_tracks поверх синхронной сетки F01."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f03_lines import Line, detect_window_lines, rms_power_spectrum
from lnt.characterization.f03_result import (
    _GRID_UNSTABLE,
    _TRACK_TOO_SHORT,
    METHOD,
    F03Result,
    _unavailable,
)
from lnt.characterization.f03_tracks import assemble_tracks
from lnt.characterization.sync_grid import (
    complete_window_count,
    nominal_window_samples,
    resampled_window,
    window_start_sample,
)
from lnt.features.tracking import PeakObservation, QualifiedPeak, track_peak_trajectories
from lnt.harmonics.constants import DFT_BINS_PER_HARMONIC

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f01_phase_cycle import F01Result

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type WindowLine = tuple[float, float, float, bool]
type PerWindow = list[tuple[int, list[WindowLine]]]

_MIN_TRACK_WINDOWS: Final = 2

__all__ = ["METHOD", "F03Result", "compute_f03_interharmonic_tracks"]


def compute_f03_interharmonic_tracks(  # noqa: PLR0913 - объявленные гейты рецепта
    samples: FloatInput,
    *,
    sample_rate_hz: float,
    f01_result: F01Result,
    window_s: float,
    bin_spacing_hz: float,
    association_tolerance_bins: int,
    detection_margin_db: float,
    local_median_bin_count: int,
    minimum_lifetime_windows: int,
    subharmonic_orders: tuple[int, ...],
    maximum_tracks: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F03Result:
    """Треки линий IHG и субгармоник на сетке F01 трекером ближайшего соседа.

    Сетка берётся из результата ``compute_f01_phase_cycle`` (F03-1): без
    ``f1_hz`` собственной оценки сети нет — UNAVAILABLE ``grid_unstable``.
    Пропуск окна рвёт трек без интерполяции: залоченное ``gap_interpolation``
    это ровно остановка билдера в ``tracking.py:99-109`` (F03-8).
    """
    # Объявленный бюджет не расходуется: работа O(W·B) по окнам и бинам
    # (спека `method-notes-families-1-9.md:194-195`), ограничивать нечего.
    _ = resources
    f1 = f01_result.f1_hz
    if f1 is None or not float(f1) > 0.0:
        return _unavailable((_GRID_UNSTABLE,), 0, 0, 0)
    fs = float(sample_rate_hz)
    signal = np.asarray(samples, dtype=np.float64)
    n_nominal = nominal_window_samples(float(window_s), fs)
    total = complete_window_count(int(signal.size), n_nominal)
    if total < _MIN_TRACK_WINDOWS:
        # Предусловие спеки:188-189; кода «запись коротка» в словаре F03 нет (F03-13).
        return _unavailable((_TRACK_TOO_SHORT,), total, 0, 0)
    tolerance_hz = float(association_tolerance_bins) * float(bin_spacing_hz)
    observations: list[PeakObservation] = []
    per_window: PerWindow = []
    below_resolution = False
    for index in range(total):
        if checkpoint is not None:
            checkpoint()
        start = window_start_sample(index, n_nominal)
        window = resampled_window(signal, fs, float(f1), start, n_nominal)
        power = rms_power_spectrum(window)
        lines, below = detect_window_lines(
            power,
            f1_hz=float(f1),
            window_s=float(window_s),
            detection_margin_db=float(detection_margin_db),
            local_median_bin_count=int(local_median_bin_count),
            subharmonic_orders=tuple(int(o) for o in subharmonic_orders),
        )
        below_resolution = below_resolution or below
        per_window.append((index, [_values(line) for line in lines]))
        observations.append(
            PeakObservation(
                window_id=f"window-{index:04d}",
                time_s=float(index) * float(window_s),
                peaks=tuple(
                    QualifiedPeak(
                        band_name=_band(line.center_hz, float(f1)),
                        frequency_hz=line.center_hz,
                    )
                    for line in lines
                ),
            )
        )
    tracks = track_peak_trajectories(tuple(observations), tolerance_hz=tolerance_hz)
    return assemble_tracks(
        tracks,
        per_window,
        total_windows=total,
        window_s=float(window_s),
        minimum_lifetime_windows=int(minimum_lifetime_windows),
        maximum_tracks=int(maximum_tracks),
        below_resolution=below_resolution,
    )


def _values(line: Line) -> WindowLine:
    """Значения линии для сборки трека: центр, амплитуда, ширина, флаг утечки."""
    return (line.center_hz, line.amplitude_v, line.width_hz, line.ambiguous)


def _band(center_hz: float, f1: float) -> str:
    """Группа IHG: квант — измеренный бин сетки ``f1/10`` (F03-8).

    Центроид он-грид линии всегда попадает в один квант, а дрожание ``1e-14``
    кванта не пересекает. Квантование допуском ассоциации запрещено: граница
    кванта может лечь ровно на центр линии и рвать трек на куски.
    """
    quantum = float(f1) / DFT_BINS_PER_HARMONIC
    return f"ihg-{int(np.floor(float(center_hz) / quantum + 0.5)):04d}"
