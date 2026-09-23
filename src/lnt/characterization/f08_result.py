"""F08 bounded_single_damped_sinusoid_fit: замороженный результат и коды."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from lnt.characterization.records import Status

METHOD: Final = "bounded_single_damped_sinusoid_fit"

CLIPPED: Final = "clipped"
SINGLE_EXPONENTIAL_POOR: Final = "single_exponential_poor"
BELOW_SNR: Final = "below_snr"
TOO_FEW_SAMPLES: Final = "too_few_samples"
OVERLAPPING_EVENTS: Final = "overlapping_events"
MULTIMODE: Final = "multimode"

DECLARED_CODES: Final = (
    CLIPPED,
    SINGLE_EXPONENTIAL_POOR,
    BELOW_SNR,
    TOO_FEW_SAMPLES,
    OVERLAPPING_EVENTS,
    MULTIMODE,
)

__all__ = [
    "BELOW_SNR",
    "CLIPPED",
    "DECLARED_CODES",
    "METHOD",
    "MULTIMODE",
    "OVERLAPPING_EVENTS",
    "SINGLE_EXPONENTIAL_POOR",
    "TOO_FEW_SAMPLES",
    "F08Result",
    "InitialSeed",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class InitialSeed:
    """Инициализация шага 2 спеки: пересечения нуля, частота и декремент.

    ``n_zc`` известен всегда, как только спан измерен; ``f_d_hz``,
    ``log_decrement`` и ``tau_d_s`` остаются ``None``, когда логарифмический
    декремент не измеряется. Отсутствие инициализации — это отказ, а не значение.
    """

    n_zc: int
    f_d_hz: float | None
    log_decrement: float | None
    tau_d_s: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class F08Result:
    """Морфология каждого объявленного события: прямые величины и параметры фита.

    ``t_rise_s``, ``v_peak_v``, ``v2_s`` и ``n_zc`` измеряются по детрендованному
    спану и публикуются всегда, когда спан измерим. ``f_d_hz``, ``tau_d_s``,
    ``zeta`` и ``residual_fraction`` происходят из фита и остаются ``None`` при
    отказе: подогнанная частота на неописанной форме была бы выдумана.
    """

    status: Status
    reason_codes: tuple[str, ...]
    t_rise_s: tuple[float | None, ...]
    v_peak_v: tuple[float | None, ...]
    v2_s: tuple[float | None, ...]
    n_zc: tuple[int | None, ...]
    f_d_hz: tuple[float | None, ...]
    tau_d_s: tuple[float | None, ...]
    zeta: tuple[float | None, ...]
    residual_fraction: tuple[float | None, ...]
    evaluated_event_count: int
    omitted_event_count: int
