"""Strict typed table blocks for characterization artifacts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.records import Unit, validate_unit_name

type TableScalar = str | int | float | bool | None


class TableValueType(StrEnum):
    """Closed table cell type vocabulary."""

    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    TEXT = "text"
    REASON_CODE = "reason_code"


@dataclass(frozen=True, slots=True, kw_only=True)
class TableColumn:
    """One exact table column."""

    name: str
    unit: Unit | None
    type: TableValueType

    def __post_init__(self) -> None:
        """Validate column type, unit, and reason naming."""
        if not self.name or (self.type is TableValueType.REASON_CODE) != self.name.endswith(
            "_reason_code"
        ):
            raise CharacterizationError("table_column", "invalid table column")
        if self.type in {TableValueType.NUMBER, TableValueType.INTEGER}:
            if self.unit is None:
                raise CharacterizationError("table_column", "numeric column requires unit")
            validate_unit_name(self.name, self.unit)
        elif self.unit is not None:
            raise CharacterizationError("table_column", "nonnumeric column cannot have unit")


@dataclass(frozen=True, slots=True, kw_only=True)
class TableBlock:
    """Bounded table with explicit full and stored row counts."""

    table_id: str
    columns: tuple[TableColumn, ...]
    rows: tuple[tuple[TableScalar, ...], ...]
    row_count: int
    stored_count: int
    selection_rule: str

    def __post_init__(self) -> None:
        """Validate table bounds, row types, and null reasons."""
        if (
            not self.table_id
            or not self.columns
            or len({column.name for column in self.columns}) != len(self.columns)
            or self.row_count < 0
            or self.stored_count != len(self.rows)
            or self.stored_count > self.row_count
            or not self.selection_rule
            or (self.selection_rule == "all" and self.stored_count != self.row_count)
        ):
            raise CharacterizationError("table_schema", "invalid table block")
        reason_indexes = {
            column.name.removesuffix("_reason_code"): index
            for index, column in enumerate(self.columns)
            if column.type is TableValueType.REASON_CODE
        }
        for row in self.rows:
            if len(row) != len(self.columns):
                raise CharacterizationError("table_row", "row width does not match columns")
            for column, value in zip(self.columns, row, strict=True):
                self._validate_cell(column, value)
                if value is None and column.type is not TableValueType.REASON_CODE:
                    reason_index = reason_indexes.get(column.name)
                    if (
                        reason_index is None
                        or not isinstance(row[reason_index], str)
                        or not row[reason_index]
                    ):
                        raise CharacterizationError(
                            "table_null_reason", f"{column.name} null requires reason code"
                        )

    @staticmethod
    def _validate_cell(column: TableColumn, value: TableScalar) -> None:
        if value is None:
            return
        valid = {
            TableValueType.NUMBER: isinstance(value, int | float) and not isinstance(value, bool),
            TableValueType.INTEGER: isinstance(value, int) and not isinstance(value, bool),
            TableValueType.BOOLEAN: isinstance(value, bool),
            TableValueType.TEXT: isinstance(value, str) and bool(value),
            TableValueType.REASON_CODE: isinstance(value, str) and bool(value),
        }[column.type]
        if not valid or (isinstance(value, float) and not math.isfinite(value)):
            raise CharacterizationError("table_cell", f"invalid value in {column.name}")
