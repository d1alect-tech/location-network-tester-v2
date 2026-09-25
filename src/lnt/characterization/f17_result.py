"""F17: объявления, полная сетка измерений и компактное хранение ячеек."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f17_contract import (
    ARTIFACT_LIMIT,
    BH_P_VALUE_NAME,
    CYCLIC_FREQUENCIES_HZ,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_FREQUENCY_OFF_GRID,
    CYCLIC_SPECTRUM_NAME,
    DECLARED_CODES,
    F17_ID,
    F17_INDEX,
    INSUFFICIENT_CYCLES,
    INSUFFICIENT_FRAMES,
    METHOD,
    NO_SIGNIFICANT_CELL,
    PHASE_REFERENCE_UNAVAILABLE,
    RAW_P_VALUE_NAME,
    SEGMENT_SUPPORT_NAME,
    ZERO_DENOMINATOR,
    F17Declarations,
)
from lnt.characterization.records import Status

type Float64Array = NDArray[np.float64]
type Complex128Array = NDArray[np.complex128]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]

__all__ = [
    "ARTIFACT_LIMIT",
    "BH_P_VALUE_NAME",
    "CYCLIC_FREQUENCIES_HZ",
    "CYCLIC_FREQUENCY_NAME",
    "CYCLIC_FREQUENCY_OFF_GRID",
    "CYCLIC_SPECTRUM_NAME",
    "DECLARED_CODES",
    "F17_ID",
    "F17_INDEX",
    "INSUFFICIENT_CYCLES",
    "INSUFFICIENT_FRAMES",
    "METHOD",
    "NO_SIGNIFICANT_CELL",
    "PHASE_REFERENCE_UNAVAILABLE",
    "RAW_P_VALUE_NAME",
    "SEGMENT_SUPPORT_NAME",
    "ZERO_DENOMINATOR",
    "F17Declarations",
    "F17Result",
    "unavailable_f17",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class F17Result:
    """Полная проверенная сетка F17 и bounded список significant cells."""

    status: Status
    reason_codes: tuple[str, ...]
    cyclic_frequencies_hz: Float64Array
    frequencies_hz: Float64Array
    cyclic_spectrum: Complex128Array
    coherence: Float64Array
    raw_p_value: Float64Array
    bh_p_value: Float64Array
    segment_support: Int64Array
    cell_available: BoolArray
    significant: BoolArray
    stored_alpha_hz: Float64Array
    stored_frequency_hz: Float64Array
    stored_cyclic_spectrum: Complex128Array
    stored_coherence: Float64Array
    stored_raw_p_value: Float64Array
    stored_bh_p_value: Float64Array
    stored_segment_support: Int64Array
    sample_count: int
    qualified_sample_count: int
    qualified_cycle_count: int
    frame_count: int
    tested_cell_count: int
    significant_cell_count: int
    stored_cell_count: int
    omitted_cell_count: int

    def __post_init__(self) -> None:
        """Проверить F17 до того, как результат уйдёт seam или bundle."""
        from lnt.characterization.f17_validation import validate_f17_result  # noqa: PLC0415

        validate_f17_result(self)

    @property
    def alpha_hz(self) -> Float64Array:
        """Совместимое имя оси declared alpha."""
        return self.cyclic_frequencies_hz

    @property
    def frequency_hz(self) -> Float64Array:
        """Совместимое имя center-frequency axis."""
        return self.frequencies_hz

    @property
    def cyclic_frequency_hz(self) -> Float64Array:
        """Совместимое имя cyclic-frequency axis."""
        return self.cyclic_frequencies_hz

    @property
    def p_value(self) -> Float64Array:
        """Совместимое имя raw p-value."""
        return self.raw_p_value

    @property
    def adjusted_p_value(self) -> Float64Array:
        """Совместимое имя BH-adjusted p-value."""
        return self.bh_p_value


def unavailable_f17(codes: tuple[str, ...], sample_count: int) -> F17Result:
    """Собрать UNAVAILABLE с пустыми доменами и честным внешним sample count."""
    empty_float = np.empty(0, dtype=np.float64)
    empty_complex = np.empty(0, dtype=np.complex128)
    empty_int = np.empty(0, dtype=np.int64)
    empty_bool = np.empty(0, dtype=np.bool_)
    return F17Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        cyclic_frequencies_hz=empty_float,
        frequencies_hz=empty_float,
        cyclic_spectrum=empty_complex,
        coherence=empty_float,
        raw_p_value=empty_float,
        bh_p_value=empty_float,
        segment_support=empty_int,
        cell_available=empty_bool,
        significant=empty_bool,
        stored_alpha_hz=empty_float,
        stored_frequency_hz=empty_float,
        stored_cyclic_spectrum=empty_complex,
        stored_coherence=empty_float,
        stored_raw_p_value=empty_float,
        stored_bh_p_value=empty_float,
        stored_segment_support=empty_int,
        sample_count=max(0, int(sample_count)),
        qualified_sample_count=0,
        qualified_cycle_count=0,
        frame_count=0,
        tested_cell_count=0,
        significant_cell_count=0,
        stored_cell_count=0,
        omitted_cell_count=0,
    )


def select_stored_cells(  # noqa: PLR0913, PLR0917 - полный набор измерений significant cells
    cyclic_spectrum: Complex128Array,
    coherence: Float64Array,
    raw_p_value: Float64Array,
    bh_p_value: Float64Array,
    segment_support: Int64Array,
    significant: BoolArray,
    *,
    maximum: int,
) -> tuple[Complex128Array, Float64Array, Float64Array, Float64Array, Int64Array, bool]:
    """Взять канонический префикс significant cells и сообщить о cap."""
    if maximum <= 0:
        raise ValueError("F17 stored-cell cap must be positive")
    flat = np.flatnonzero(np.asarray(significant, dtype=np.bool_).ravel())
    kept = flat[: int(maximum)]
    omitted = int(flat.size - kept.size)
    return (
        np.asarray(cyclic_spectrum).ravel()[kept],
        np.asarray(coherence).ravel()[kept],
        np.asarray(raw_p_value).ravel()[kept],
        np.asarray(bh_p_value).ravel()[kept],
        np.asarray(segment_support).ravel()[kept],
        omitted > 0,
    )
