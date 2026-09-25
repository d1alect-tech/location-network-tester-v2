"""F12: таблица locked conventions, inventory и дословной границы притязаний."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f12_contract import (
    ADJUSTED_P_VALUE_NAME,
    BH_SCOPE,
    CAP_STORAGE_CONVENTION,
    CLAIM_BOUNDARY,
    CONJUGATE_SYMMETRY_CONVENTION,
    F12_ID,
    F12_INDEX,
    FRAME_COUNT_NAME,
    FREQUENCY_AXIS_NAME,
    MAXIMUM_SPECTRAL_KURTOSIS_NAME,
    MAXIMUM_TIE_BREAK,
    METHOD,
    NULL_SCOPE,
    RANDOM_PHASE_CONVENTION,
    SCALE_INDEX_NAME,
    SEGMENT_SAMPLES,
    SELECTED_BAND_CONVENTION,
    SELECTED_BAND_HIGH_NAME,
    SELECTED_BAND_LOW_NAME,
    SPECTRAL_KURTOSIS_NAME,
    SURROGATE_PHASE_MEAN_CONVENTION,
    SURROGATE_SUPPORT_NAME,
    WINDOW_SUPPORT_NAME,
)
from lnt.characterization.f12_result import F12Declarations
from lnt.characterization.records import Unit
from lnt.characterization.tables import TableBlock, TableColumn, TableScalar, TableValueType

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily

__all__ = ["KURTOSIS_TABLE_ID", "kurtosis_metadata", "locked_declarations"]

KURTOSIS_TABLE_ID: Final = "f12_kurtosis_metadata"
METHOD_VERSION: Final = 1
_ROW_COUNT: Final = 1
_TEXT: Final = TableValueType.TEXT
_COUNT: Final = (Unit.COUNT, TableValueType.INTEGER)
_RATIO: Final = (Unit.RATIO, TableValueType.NUMBER)
_HZ: Final = (Unit.HZ, TableValueType.NUMBER)

# Зеркало closed unit vocabulary из f12_units.validate_f12_units: инвентарь
# persisted quantity names с их объявленными единицами, без пересказа.
_QUANTITY_UNITS: Final = (
    (SPECTRAL_KURTOSIS_NAME, Unit.RATIO),
    (ADJUSTED_P_VALUE_NAME, Unit.RATIO),
    (MAXIMUM_SPECTRAL_KURTOSIS_NAME, Unit.RATIO),
    (FREQUENCY_AXIS_NAME, Unit.HZ),
    (SELECTED_BAND_LOW_NAME, Unit.HZ),
    (SELECTED_BAND_HIGH_NAME, Unit.HZ),
    (FRAME_COUNT_NAME, Unit.COUNT),
    (SCALE_INDEX_NAME, Unit.COUNT),
    (SURROGATE_SUPPORT_NAME, Unit.COUNT),
    (WINDOW_SUPPORT_NAME, Unit.COUNT),
)
type _Cell = tuple[str, Unit | None, TableValueType, TableScalar]


def kurtosis_metadata(declarations: F12Declarations) -> TableBlock:
    """Сохранить recipe surface, все conventions и claim boundary без пересказа."""
    cells = _cells(declarations)
    return TableBlock(
        table_id=KURTOSIS_TABLE_ID,
        columns=tuple(
            TableColumn(name=name, unit=unit, type=kind) for name, unit, kind, _ in cells
        ),
        rows=(tuple(value for _, _, _, value in cells),),
        row_count=_ROW_COUNT,
        stored_count=_ROW_COUNT,
        selection_rule="all",
    )


def locked_declarations(family: CharacterizationFamily) -> F12Declarations:
    """Прочитать recipe surface и отвергнуть любой дрейф locked F12 recipe."""
    declarations = _declarations(family)
    if declarations != F12Declarations.locked():
        raise CharacterizationError("status_invariant", "F12 recipe declarations are not locked")
    return declarations


def _declarations(family: CharacterizationFamily) -> F12Declarations:
    try:
        return F12Declarations(
            phase_bins=_integer(family.value("phase_bins")),
            segment_samples=_integers(family.value("segment_samples")),
            window=_text(family.value("window")),
            overlap_fraction=_number(family.value("overlap_fraction")),
            detrend=_text(family.value("detrend")),
            analysis_low_hz=_number(family.value("analysis_low_hz")),
            analysis_high_hz=_number(family.value("analysis_high_hz")),
            nyquist_fraction_max=_number(family.value("nyquist_fraction_max")),
            minimum_frames=_integer(family.value("minimum_frames")),
            surrogate=_text(family.value("surrogate")),
            surrogate_count=_integer(family.value("surrogate_count")),
            surrogate_seed=_integer(family.value("surrogate_seed")),
            search_adjustment=_text(family.value("search_adjustment")),
            multiple_testing=_text(family.value("multiple_testing")),
            false_discovery_rate=_number(family.value("false_discovery_rate")),
            maximum_stored_bins=_integer(family.value("maximum_stored_bins")),
        )
    except ValueError as error:
        raise CharacterizationError(
            "status_invariant", "F12 recipe declarations are invalid"
        ) from error


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CharacterizationError("status_invariant", "F12 recipe value must be text")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("status_invariant", "F12 recipe value must be an integer")
    return value


def _integers(value: object) -> tuple[int, ...]:
    if not isinstance(value, tuple | list) or not value:
        raise CharacterizationError("status_invariant", "F12 recipe axis has wrong shape")
    return tuple(_integer(item) for item in value)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CharacterizationError("status_invariant", "F12 recipe value must be a number")
    return float(value)


def _cells(declarations: F12Declarations) -> tuple[_Cell, ...]:
    """Собрать единственную строку метаданных в объявленном порядке колонок."""
    identity: tuple[_Cell, ...] = (
        ("family_id", None, _TEXT, F12_ID),
        ("family_index", *_COUNT, F12_INDEX),
        ("method", None, _TEXT, METHOD),
        ("method_version", *_COUNT, METHOD_VERSION),
        ("segment_samples_count", *_COUNT, len(SEGMENT_SAMPLES)),
    )
    declared: tuple[_Cell, ...] = (
        ("phase_bins", *_COUNT, declarations.phase_bins),
        ("window", None, _TEXT, declarations.window),
        ("overlap_fraction", *_RATIO, declarations.overlap_fraction),
        ("detrend", None, _TEXT, declarations.detrend),
        ("analysis_low_hz", *_HZ, declarations.analysis_low_hz),
        ("analysis_high_hz", *_HZ, declarations.analysis_high_hz),
        ("nyquist_fraction_max", *_RATIO, declarations.nyquist_fraction_max),
        ("minimum_frames", *_COUNT, declarations.minimum_frames),
        ("surrogate", None, _TEXT, declarations.surrogate),
        ("surrogate_count", *_COUNT, declarations.surrogate_count),
        ("surrogate_seed", *_COUNT, declarations.surrogate_seed),
        ("search_adjustment", None, _TEXT, declarations.search_adjustment),
        ("multiple_testing", None, _TEXT, declarations.multiple_testing),
        ("false_discovery_rate", *_RATIO, declarations.false_discovery_rate),
        ("maximum_stored_bins", *_COUNT, declarations.maximum_stored_bins),
    )
    conventions: tuple[_Cell, ...] = (
        ("bh_scope", None, _TEXT, BH_SCOPE),
        ("maximum_tie_break", None, _TEXT, MAXIMUM_TIE_BREAK),
        ("selected_band_convention", None, _TEXT, SELECTED_BAND_CONVENTION),
        ("cap_storage_convention", None, _TEXT, CAP_STORAGE_CONVENTION),
        ("null_scope", None, _TEXT, NULL_SCOPE),
        ("surrogate_phase_mean_convention", None, _TEXT, SURROGATE_PHASE_MEAN_CONVENTION),
        ("random_phase_convention", None, _TEXT, RANDOM_PHASE_CONVENTION),
        ("conjugate_symmetry_convention", None, _TEXT, CONJUGATE_SYMMETRY_CONVENTION),
    )
    inventory = "|".join(f"{name}:{unit.value}" for name, unit in _QUANTITY_UNITS)
    return (
        *identity,
        *declared,
        *conventions,
        ("quantity_units", None, _TEXT, inventory),
        ("claim_boundary", None, _TEXT, CLAIM_BOUNDARY),
    )
