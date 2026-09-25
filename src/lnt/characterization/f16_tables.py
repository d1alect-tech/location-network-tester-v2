"""F16: таблица locked conventions и дословной границы притязаний."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f16_contract import (
    ACF_AGGREGATION,
    ANALYZED_SEGMENT_CONVENTION,
    CLAIM_BOUNDARY,
    COUNT_WINDOW_CONVENTION,
    LAG_SAMPLE_CONVENTION,
    MAD_CONVENTION,
)
from lnt.characterization.records import Unit
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    from lnt.characterization.f16_result import F16Declarations

MEMORY_TABLE_ID: Final = "f16_memory_metadata"
_ROW_COUNT: Final = 1


def memory_metadata(declarations: F16Declarations) -> TableBlock:
    """Сохранить recipe surface, все conventions и claim boundary без пересказа."""
    return TableBlock(
        table_id=MEMORY_TABLE_ID,
        columns=(
            TableColumn(name="autocovariance", unit=None, type=TableValueType.TEXT),
            TableColumn(name="phase_bins", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(
                name="count_window_overlap_fraction",
                unit=Unit.RATIO,
                type=TableValueType.NUMBER,
            ),
            TableColumn(name="partial_count_window_handling", unit=None, type=TableValueType.TEXT),
            TableColumn(name="fano_variance_ddof", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="minimum_pairs", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="minimum_count_windows", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(
                name="maximum_fft_segment_samples",
                unit=Unit.COUNT,
                type=TableValueType.INTEGER,
            ),
            TableColumn(name="lag_sample_convention", unit=None, type=TableValueType.TEXT),
            TableColumn(name="mad_convention", unit=None, type=TableValueType.TEXT),
            TableColumn(name="acf_aggregation", unit=None, type=TableValueType.TEXT),
            TableColumn(name="analyzed_segment_convention", unit=None, type=TableValueType.TEXT),
            TableColumn(name="count_window_convention", unit=None, type=TableValueType.TEXT),
            TableColumn(name="claim_boundary", unit=None, type=TableValueType.TEXT),
        ),
        rows=(
            (
                declarations.autocovariance,
                declarations.phase_bins,
                declarations.count_window_overlap_fraction,
                declarations.partial_count_window_handling,
                declarations.fano_variance_ddof,
                declarations.minimum_pairs,
                declarations.minimum_count_windows,
                declarations.maximum_fft_segment_samples,
                LAG_SAMPLE_CONVENTION,
                MAD_CONVENTION,
                ACF_AGGREGATION,
                ANALYZED_SEGMENT_CONVENTION,
                COUNT_WINDOW_CONVENTION,
                CLAIM_BOUNDARY,
            ),
        ),
        row_count=_ROW_COUNT,
        stored_count=_ROW_COUNT,
        selection_rule="all",
    )
