"""F17: таблица locked conventions, quantity names и границы притязаний."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f17_contract import (
    BH_P_VALUE_NAME,
    CHANNEL_PRODUCT_CONVENTION,
    CLAIM_BOUNDARY,
    COHERENCE_NAME,
    CYCLE_CONCATENATION_CONVENTION,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_SPECTRUM_NAME,
    F17_ID,
    F17_INDEX,
    FREQUENCY_MAPPING,
    FREQUENCY_NAME,
    METHOD,
    METHOD_VERSION,
    NULL_PERMUTATION_CONVENTION,
    RAW_P_VALUE_NAME,
    SEGMENT_SUPPORT_NAME,
    SPEC_GAPS,
)
from lnt.characterization.records import Unit
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    from lnt.characterization.f17_contract import F17Declarations

COHERENCE_TABLE_ID: Final = "f17_coherence_metadata"
_ROW_COUNT: Final = 1
_TEXT: Final = TableValueType.TEXT
_COUNT: Final = TableValueType.INTEGER
_NUMBER: Final = TableValueType.NUMBER

type Cell = tuple[str, TableValueType, Unit | None, str | int | float]


def coherence_metadata(declarations: F17Declarations) -> TableBlock:
    """Сохранить recipe surface, все conventions, quantity names и claim boundary."""
    spec = _spec(declarations)
    return TableBlock(
        table_id=COHERENCE_TABLE_ID,
        columns=tuple(TableColumn(name=name, unit=unit, type=kind) for name, kind, unit, _ in spec),
        rows=(tuple(value for _, _, _, value in spec),),
        row_count=_ROW_COUNT,
        stored_count=_ROW_COUNT,
        selection_rule="all",
    )


def _spec(declarations: F17Declarations) -> tuple[Cell, ...]:
    """Одна спецификация колонок и их значений: columns и row не могут разъехаться."""
    return (
        ("family_id", _TEXT, None, F17_ID),
        ("family_index", _COUNT, Unit.COUNT, F17_INDEX),
        ("method", _TEXT, None, METHOD),
        ("method_version", _COUNT, Unit.COUNT, METHOD_VERSION),
        ("phase_bins", _COUNT, Unit.COUNT, declarations.phase_bins),
        ("segment_samples", _COUNT, Unit.COUNT, declarations.segment_samples),
        ("surrogate_count", _COUNT, Unit.COUNT, declarations.surrogate_count),
        ("surrogate_seed", _COUNT, Unit.COUNT, declarations.surrogate_seed),
        ("minimum_complete_cycles", _COUNT, Unit.COUNT, declarations.minimum_complete_cycles),
        ("minimum_frames", _COUNT, Unit.COUNT, declarations.minimum_frames),
        ("maximum_stored_cells", _COUNT, Unit.COUNT, declarations.maximum_stored_cells),
        ("overlap_fraction", _NUMBER, Unit.RATIO, declarations.overlap_fraction),
        ("nyquist_fraction_max", _NUMBER, Unit.RATIO, declarations.nyquist_fraction_max),
        ("false_discovery_rate", _NUMBER, Unit.RATIO, declarations.false_discovery_rate),
        ("analysis_low_hz", _NUMBER, Unit.HZ, declarations.analysis_low_hz),
        ("analysis_high_hz", _NUMBER, Unit.HZ, declarations.analysis_high_hz),
        ("window", _TEXT, None, declarations.window),
        # frequency_mapping берётся из locked constant, а не из параметра: F17Declarations
        # уже закрепляет равенство, а decode сверяет таблицу с F17Declarations.locked().
        ("frequency_mapping", _TEXT, None, FREQUENCY_MAPPING),
        ("surrogate", _TEXT, None, declarations.surrogate),
        ("multiple_testing", _TEXT, None, declarations.multiple_testing),
        ("cycle_concatenation_convention", _TEXT, None, CYCLE_CONCATENATION_CONVENTION),
        ("null_permutation_convention", _TEXT, None, NULL_PERMUTATION_CONVENTION),
        ("channel_product_convention", _TEXT, None, CHANNEL_PRODUCT_CONVENTION),
        ("claim_boundary", _TEXT, None, CLAIM_BOUNDARY),
        ("spec_gap_f17_1", _TEXT, None, SPEC_GAPS[0]),
        ("frequency_quantity_name", _TEXT, None, FREQUENCY_NAME),
        ("cyclic_frequency_quantity_name", _TEXT, None, CYCLIC_FREQUENCY_NAME),
        ("cyclic_spectrum_quantity_name", _TEXT, None, CYCLIC_SPECTRUM_NAME),
        ("coherence_quantity_name", _TEXT, None, COHERENCE_NAME),
        ("raw_p_value_quantity_name", _TEXT, None, RAW_P_VALUE_NAME),
        ("bh_p_value_quantity_name", _TEXT, None, BH_P_VALUE_NAME),
        ("segment_support_quantity_name", _TEXT, None, SEGMENT_SUPPORT_NAME),
        ("stored_alpha_quantity_name", _TEXT, None, "f17_stored_alpha_hz"),
        ("stored_frequency_quantity_name", _TEXT, None, "f17_stored_frequency_hz"),
        ("stored_cyclic_spectrum_quantity_name", _TEXT, None, "f17_stored_cyclic_spectrum_v2"),
        ("stored_coherence_quantity_name", _TEXT, None, "f17_stored_coherence"),
        ("stored_raw_p_value_quantity_name", _TEXT, None, "f17_stored_raw_p_value"),
        ("stored_bh_p_value_quantity_name", _TEXT, None, "f17_stored_bh_p_value"),
        ("stored_segment_support_quantity_name", _TEXT, None, "f17_stored_segment_support"),
    )
