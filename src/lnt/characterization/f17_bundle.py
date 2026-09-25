"""F17: persistence mapper для cyclic spectral coherence сетки ячеек."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f17_arrays import COUNTER_FIELDS, published
from lnt.characterization.f17_contract import (
    ARTIFACT_LIMIT,
    CYCLIC_FREQUENCIES_HZ,
    DECLARED_CODES,
    F17_ID,
    F17_INDEX,
    INSUFFICIENT_CYCLES,
    INSUFFICIENT_FRAMES,
    MAXIMUM_STORED_CELLS,
    METHOD,
    METHOD_VERSION,
    MINIMUM_COMPLETE_CYCLES,
    MINIMUM_FRAMES,
    NO_SIGNIFICANT_CELL,
    PHASE_REFERENCE_UNAVAILABLE,
    F17Declarations,
)
from lnt.characterization.f17_decode import decode_f17_result
from lnt.characterization.f17_tables import COHERENCE_TABLE_ID, coherence_metadata
from lnt.characterization.f17_validation import validate_f17_result
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    zero_support,
)
from lnt.characterization.models import FamilyResult, TableReference
from lnt.characterization.records import (
    Band,
    ScalarSummary,
    SignalPlane,
    Status,
    Support,
    Unit,
    Window,
)

if TYPE_CHECKING:
    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f17_result import F17Result
    from lnt.characterization.tables import TableBlock

__all__ = [
    "COHERENCE_TABLE_ID",
    "F17_ID",
    "F17_INDEX",
    "build_f17_family",
    "decode_f17_result",
]

_F17_UNITS: Final = (Unit.HZ, Unit.V2, Unit.RATIO, Unit.COUNT)
_WINDOW_KIND: Final = "record"
_TABLE_ROLE: Final = "coherence_metadata"
# Коды, которые движок публикует только вместе с UNAVAILABLE. cyclic_frequency_off_grid
# и zero_denominator сюда НЕ входят: f17_reasons публикует их и на построенной сетке.
_TERMINAL_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    INSUFFICIENT_CYCLES,
    INSUFFICIENT_FRAMES,
)
# Коды, которые движок публикует только вместе с построенной сеткой.
_PARTIAL_CODES: Final = (NO_SIGNIFICANT_CELL, ARTIFACT_LIMIT)


def build_f17_family(
    result: F17Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Собрать F17 envelope, finite arrays и таблицу conventions."""
    if family.id != F17_ID or family.method != METHOD or family.method_version != METHOD_VERSION:
        raise CharacterizationError("family_order", "f17 mapper needs the f17 family")
    declarations = _locked_declarations(_declarations(family))
    reasons = _checked_codes(result.reason_codes)
    span = _span(record_duration_s)
    _status(result.status, reasons)
    validate_f17_result(result)
    if result.status is Status.UNAVAILABLE:
        spec = _spec(family, band, span, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}, {}
    arrays, references = published(result, declarations, partial=result.status is Status.PARTIAL)
    spec = _spec(family, band, span, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(result, span, reasons),
        array_refs=tuple(references),
        table_refs=(TableReference(table_id=COHERENCE_TABLE_ID, role=_TABLE_ROLE),),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays, {COHERENCE_TABLE_ID: coherence_metadata(declarations)}


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if (
        any(code not in DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "f17 reasons are not canonical")
    return codes


def _status(status: object, reasons: tuple[str, ...]) -> None:
    if not isinstance(status, Status):
        raise CharacterizationError("status_invariant", "unknown F17 status")
    if (status is Status.AVAILABLE and reasons) or (status is not Status.AVAILABLE and not reasons):
        raise CharacterizationError("status_invariant", "invalid F17 status/reasons")
    if status is Status.PARTIAL and any(code in _TERMINAL_CODES for code in reasons):
        raise CharacterizationError("status_invariant", "terminal F17 reason cannot be partial")
    if status is Status.PARTIAL and not any(code in _PARTIAL_CODES for code in reasons):
        raise CharacterizationError("status_invariant", "f17 partial needs a declared reason")
    if status is Status.UNAVAILABLE and any(code in _PARTIAL_CODES for code in reasons):
        raise CharacterizationError("status_invariant", "f17 partial reason cannot be unavailable")


def _span(value: float) -> float:
    span = float(value)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "f17 record duration must be positive")
    return span


def _counts(result: F17Result, reasons: tuple[str, ...]) -> tuple[int, int]:
    """Перепроверить опору построенной сетки строже, чем это делает движок.

    Движок принимает нулевой tested_cell_count и frame_count больше compact record;
    оба случая означали бы выдуманную опору, поэтому конверт их не публикует.
    """
    sample = _count(result.sample_count, "sample_count")
    qualified = _count(result.qualified_sample_count, "qualified_sample_count")
    cycles = _count(result.qualified_cycle_count, "qualified_cycle_count")
    frames = _count(result.frame_count, "frame_count")
    tested = _count(result.tested_cell_count, "tested_cell_count")
    stored = _count(result.stored_cell_count, "stored_cell_count")
    significant = _count(result.significant_cell_count, "significant_cell_count")
    omitted = _count(result.omitted_cell_count, "omitted_cell_count")
    cells = len(CYCLIC_FREQUENCIES_HZ) * int(result.frequencies_hz.size)
    if not 1 <= qualified <= sample:
        raise CharacterizationError("status_invariant", "invalid f17 qualified support")
    if cycles < MINIMUM_COMPLETE_CYCLES or frames < MINIMUM_FRAMES:
        raise CharacterizationError("status_invariant", "f17 support floor is not declared")
    if frames > qualified:
        raise CharacterizationError("status_invariant", "f17 frame support exceeds the record")
    if not 1 <= tested <= cells:
        raise CharacterizationError("status_invariant", "f17 must publish a tested F17 cell")
    # Cap ограничивает COUNT хранимых ячеек, а не declared RANGE сетки: сетка публикуется
    # целиком, а пропуск префикса обязан быть объявлен как artifact_limit.
    if stored > significant or stored > MAXIMUM_STORED_CELLS:
        raise CharacterizationError("status_invariant", "f17 stored cells exceed the declared cap")
    if omitted and ARTIFACT_LIMIT not in reasons:
        raise CharacterizationError("status_invariant", "f17 stored-cell cap must report a reason")
    if omitted != significant - stored:
        raise CharacterizationError(
            "status_invariant", "f17 stored-cell accounting is inconsistent"
        )
    return sample, qualified


def _support(result: F17Result, span: float, reasons: tuple[str, ...]) -> Support:
    sample, qualified = _counts(result, reasons)
    return Support(
        start_s=0.0,
        end_s=span,
        duration_s=span,
        sample_count=sample,
        observation_count=qualified,
        missing_count=sample - qualified,
        stored_count=qualified,
        selection_rule="all",
    )


def _summaries(result: F17Result) -> tuple[ScalarSummary, ...]:
    return tuple(
        ScalarSummary(name=f"f17_{name}", value=float(getattr(result, name)), unit=Unit.COUNT)
        for name in COUNTER_FIELDS
    )


def _spec(
    family: CharacterizationFamily,
    band: Band,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F17_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F17_UNITS,
        # Запись целиком; declared STFT overlap живёт в metadata table, а не здесь.
        window=Window(
            kind=_WINDOW_KIND,
            duration_s=span,
            sample_count=None,
            overlap_fraction=0.0,
        ),
        band=band,
        signal_plane=SignalPlane.CROSS_CHANNEL,
    )


def _locked_declarations(declarations: F17Declarations) -> F17Declarations:
    if declarations != F17Declarations.locked():
        raise CharacterizationError("status_invariant", "F17 recipe declarations are not locked")
    return declarations


def _declarations(family: CharacterizationFamily) -> F17Declarations:
    try:
        return F17Declarations(
            phase_bins=_integer(family.value("phase_bins")),
            cyclic_frequencies_hz=_numbers(family.value("cyclic_frequencies_hz")),
            segment_samples=_integer(family.value("segment_samples")),
            window=_text(family.value("window")),
            overlap_fraction=_number(family.value("overlap_fraction")),
            analysis_low_hz=_number(family.value("analysis_low_hz")),
            analysis_high_hz=_number(family.value("analysis_high_hz")),
            nyquist_fraction_max=_number(family.value("nyquist_fraction_max")),
            frequency_mapping=_text(family.value("frequency_mapping")),
            surrogate=_text(family.value("surrogate")),
            surrogate_count=_integer(family.value("surrogate_count")),
            surrogate_seed=_integer(family.value("surrogate_seed")),
            multiple_testing=_text(family.value("multiple_testing")),
            false_discovery_rate=_number(family.value("false_discovery_rate")),
            minimum_complete_cycles=_integer(family.value("minimum_complete_cycles")),
            minimum_frames=_integer(family.value("minimum_frames")),
            maximum_stored_cells=_integer(family.value("maximum_stored_cells")),
        )
    except ValueError as error:
        raise CharacterizationError(
            "status_invariant", "F17 recipe declarations are invalid"
        ) from error


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CharacterizationError("status_invariant", "F17 recipe value must be text")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("status_invariant", "F17 recipe value must be an integer")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CharacterizationError("status_invariant", "F17 recipe value must be a number")
    return float(value)


def _numbers(value: object) -> tuple[float, ...]:
    if not isinstance(value, tuple | list) or not value:
        raise CharacterizationError("status_invariant", "F17 recipe axis has wrong shape")
    return tuple(_number(item) for item in value)


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CharacterizationError("status_invariant", f"f17 {name} must be a nonnegative integer")
    return value
