"""F07 two_window_real_cepstrum_and_sideband_symmetry: замороженный результат и коды."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from lnt.characterization.records import Status

METHOD: Final = "two_window_real_cepstrum_and_sideband_symmetry"

HARMONIC_COMB_ONLY: Final = "harmonic_comb_only"
WINDOW_DEPENDENT: Final = "window_dependent"
NO_DOMINANT_QUEFRENCY: Final = "no_dominant_quefrency"
BELOW_RESOLUTION: Final = "below_resolution"
LOG_FLOOR_UNSTABLE: Final = "log_floor_unstable"

DECLARED_CODES: Final = (
    HARMONIC_COMB_ONLY,
    WINDOW_DEPENDENT,
    NO_DOMINANT_QUEFRENCY,
    BELOW_RESOLUTION,
    LOG_FLOOR_UNSTABLE,
)

__all__ = [
    "BELOW_RESOLUTION",
    "DECLARED_CODES",
    "HARMONIC_COMB_ONLY",
    "LOG_FLOOR_UNSTABLE",
    "METHOD",
    "NO_DOMINANT_QUEFRENCY",
    "WINDOW_DEPENDENT",
    "F07Result",
    "_unavailable",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class F07Result:
    """Скалярный результат F07: шаг, симметрия боковых, квефренси и амплитуда."""

    status: Status
    reason_codes: tuple[str, ...]
    df_hz: float | None
    sym_db: float | None
    q_s: float | None
    quefrency_amplitude: float | None
    carrier_bin: int | None
    sample_count: int
    observation_count: int
    missing_count: int
    stored_count: int


def _unavailable(codes: tuple[str, ...]) -> F07Result:
    """Отказ без выдуманных скаляров: None вместо величин, счётчики честны."""
    return F07Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        df_hz=None,
        sym_db=None,
        q_s=None,
        quefrency_amplitude=None,
        carrier_bin=None,
        sample_count=1,
        observation_count=0,
        missing_count=1,
        stored_count=0,
    )
