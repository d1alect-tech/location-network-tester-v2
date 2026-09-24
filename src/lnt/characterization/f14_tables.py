"""F14: таблица направлений и декларативной границы интерпретации."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f14_contract import CLAIM_BOUNDARY, LAG_SIGN_CONVENTION
from lnt.characterization.records import Unit
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    from lnt.characterization.f14_result import F14Declarations, F14Result

DIRECTION_TABLE_ID: Final = "f14_direction_metadata"
_DIRECTION_COUNT: Final = 2


def direction_metadata(result: F14Result, declarations: F14Declarations) -> TableBlock:
    """Сохранить каждое направление, его учёт и границы смысла lag-поля."""
    starts: list[int] = []
    offset = 0
    for direction in result.directions:
        starts.append(offset)
        offset += int(direction.nearest_lag_s.size)
    rows = tuple(
        (
            index,
            direction.trigger_channel,
            direction.response_channel,
            int(direction.total_event_count),
            int(direction.qualified_trigger_count),
            int(direction.stored_trigger_count),
            int(direction.omitted_trigger_count),
            int(direction.boundary_trigger_count),
            int(direction.gap_crossing_trigger_count),
            int(direction.window_truncated_count),
            starts[index],
            int(direction.nearest_lag_s.size),
            int(direction.stored_trigger_count - direction.nearest_lag_s.size),
            LAG_SIGN_CONVENTION,
            CLAIM_BOUNDARY,
            declarations.nearest_event_tie_break,
            declarations.boundary_handling,
        )
        for index, direction in enumerate(result.directions)
    )
    return TableBlock(
        table_id=DIRECTION_TABLE_ID,
        columns=(
            TableColumn(name="direction_index", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="trigger_channel", unit=None, type=TableValueType.TEXT),
            TableColumn(name="response_channel", unit=None, type=TableValueType.TEXT),
            TableColumn(name="total_event_count", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(
                name="qualified_trigger_count", unit=Unit.COUNT, type=TableValueType.INTEGER
            ),
            TableColumn(name="stored_trigger_count", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="omitted_trigger_count", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(
                name="boundary_trigger_count", unit=Unit.COUNT, type=TableValueType.INTEGER
            ),
            TableColumn(
                name="gap_crossing_trigger_count", unit=Unit.COUNT, type=TableValueType.INTEGER
            ),
            TableColumn(
                name="window_truncated_count", unit=Unit.COUNT, type=TableValueType.INTEGER
            ),
            TableColumn(name="nearest_lag_start", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="nearest_lag_count", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(
                name="nearest_lag_missing_count", unit=Unit.COUNT, type=TableValueType.INTEGER
            ),
            TableColumn(name="lag_sign_convention", unit=None, type=TableValueType.TEXT),
            TableColumn(name="claim_boundary", unit=None, type=TableValueType.TEXT),
            TableColumn(name="nearest_event_tie_break", unit=None, type=TableValueType.TEXT),
            TableColumn(name="boundary_handling", unit=None, type=TableValueType.TEXT),
        ),
        rows=rows,
        row_count=_DIRECTION_COUNT,
        stored_count=len(rows),
        selection_rule="all",
    )
