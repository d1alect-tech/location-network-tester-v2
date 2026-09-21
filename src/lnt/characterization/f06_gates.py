"""F06 declared gates: co-dominant band components, SNR, envelope floor, aliasing."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f06_stream import GATE_SEGMENT_SAMPLES

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.characterization.f06_stream import Trajectory

type BoolArray = NDArray[np.bool_]

MULTIPLE_COMPONENTS: Final = "multiple_components"
LOW_SNR: Final = "low_snr"
ENVELOPE_ZERO: Final = "envelope_zero"
BAND_INVALID: Final = "band_invalid"
PHASE_ALIASED: Final = "phase_aliased"
DECLARED_CODES: Final = (MULTIPLE_COMPONENTS, LOW_SNR, ENVELOPE_ZERO, BAND_INVALID, PHASE_ALIASED)

__all__ = ["BAND_INVALID", "DECLARED_CODES", "gate_reasons", "spectral_gates"]


def spectral_gates(
    trajectory: Trajectory, low_hz: float, high_hz: float, margin_db: float
) -> tuple[float | None, int | None]:
    """Совместно доминирующие компоненты полосы и отношение сигнал/шум.

    Условие Бедросяна проверяется как «в полосе одна доминирующая компонента»: считаются
    связные области спектра СИГНАЛА, отстоящие от сильнейшей не более чем на объявленный
    ``minimum_snr_db``. Спектр огибающей не считается намеренно: на несущей в нём сидит
    пыль двойной точности (замерено около -133 дБ от линии модуляции), и относительный
    порог принимал бы её за компоненту.
    """
    if trajectory.segments == 0:
        return None, None
    frequency = np.fft.rfftfreq(GATE_SEGMENT_SAMPLES, d=1.0 / trajectory.sample_rate_hz)
    in_band = (frequency >= low_hz) & (frequency < high_hz)
    if not bool(np.any(in_band)):
        return None, None
    signal_psd = trajectory.signal_sum / trajectory.segments
    peak = float(np.max(signal_psd[in_band]))
    if peak <= 0.0:
        return -math.inf, None
    margin = 10.0 ** (margin_db / 10.0)
    components = _regions(in_band & (signal_psd >= peak / margin))
    median = float(np.median(signal_psd[in_band]))
    if median <= 0.0:
        return math.inf, components
    return 10.0 * math.log10(peak / median), components


def gate_reasons(  # noqa: PLR0913 - объявленные гейты рецепта
    trajectory: Trajectory,
    *,
    snr_db: float | None,
    components: int | None,
    minimum_snr_db: float,
    maximum_components_in_band: int,
    envelope_zero_fraction_of_median: float,
) -> tuple[str, ...]:
    """Сработавшие объявленные коды в порядке объявления."""
    amplitudes = trajectory.amplitudes[: trajectory.count]
    median = float(np.median(amplitudes)) if amplitudes.size else 0.0
    fired = {
        MULTIPLE_COMPONENTS: components is not None
        and components > int(maximum_components_in_band),
        LOW_SNR: snr_db is not None and snr_db < minimum_snr_db,
        ENVELOPE_ZERO: amplitudes.size > 0
        and bool(np.any(amplitudes <= envelope_zero_fraction_of_median * median)),
        BAND_INVALID: False,
        PHASE_ALIASED: trajectory.max_increment > trajectory.floor_rad,
    }
    return tuple(code for code in DECLARED_CODES if fired[code])


def _regions(mask: BoolArray) -> int:
    """Число связных областей выше порога."""
    if not bool(np.any(mask)):
        return 0
    edges = np.diff(mask.astype(np.int8))
    return int(np.count_nonzero(edges == 1)) + int(bool(mask[0]))
