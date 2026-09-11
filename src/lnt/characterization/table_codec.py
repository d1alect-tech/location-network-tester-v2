"""Canonical strict tables JSON codec."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.records import Unit
from lnt.characterization.tables import TableBlock, TableColumn, TableScalar, TableValueType
from lnt.context.json_codec import JsonValue, decode_object, encode_canonical
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Mapping


def encode_tables(tables: Mapping[str, TableBlock]) -> bytes:
    """Encode sorted exact table blocks as canonical JSON."""
    return encode_canonical(
        {
            "schema_version": 1,
            "tables": [
                {
                    "table_id": table.table_id,
                    "columns": [
                        {
                            "name": column.name,
                            "unit": column.unit.value if column.unit else None,
                            "type": column.type.value,
                        }
                        for column in table.columns
                    ],
                    "rows": [list(row) for row in table.rows],
                    "row_count": table.row_count,
                    "stored_count": table.stored_count,
                    "selection_rule": table.selection_rule,
                }
                for _, table in sorted(tables.items())
            ],
        },
        "characterization tables",
    )


def decode_tables(data: bytes) -> dict[str, TableBlock]:
    """Decode canonical table JSON with exact closed fields."""
    try:
        raw = decode_object(data.decode("utf-8"), "characterization tables")
    except (InputError, UnicodeDecodeError, ValueError) as error:
        raise CharacterizationError("table_json", "invalid tables JSON") from error
    _exact(raw, {"schema_version", "tables"}, "tables root")
    if raw["schema_version"] != 1 or not isinstance(raw["tables"], list):
        raise CharacterizationError("table_schema", "unsupported tables schema")
    result: dict[str, TableBlock] = {}
    for value in raw["tables"]:
        table = _parse_table(_mapping(value, "table"))
        if table.table_id in result:
            raise CharacterizationError("table_schema", "duplicate table id")
        result[table.table_id] = table
    if tuple(result) != tuple(sorted(result)) or encode_tables(result) != data:
        raise CharacterizationError("canonical_json", "tables JSON is not canonical")
    return result


def _parse_table(raw: dict[str, JsonValue]) -> TableBlock:
    _exact(
        raw, {"table_id", "columns", "rows", "row_count", "stored_count", "selection_rule"}, "table"
    )
    columns_raw = _list(raw["columns"], "columns")
    rows_raw = _list(raw["rows"], "rows")
    columns = tuple(_parse_column(_mapping(value, "column")) for value in columns_raw)
    rows: list[tuple[TableScalar, ...]] = []
    for value in rows_raw:
        row = _list(value, "row")
        if any(not isinstance(cell, str | int | float | bool) and cell is not None for cell in row):
            raise CharacterizationError("table_cell", "nested table values are forbidden")
        rows.append(
            tuple(
                cell for cell in row if isinstance(cell, str | int | float | bool) or cell is None
            )
        )
    return TableBlock(
        table_id=_string(raw["table_id"], "table_id"),
        columns=columns,
        rows=tuple(rows),
        row_count=_integer(raw["row_count"], "row_count"),
        stored_count=_integer(raw["stored_count"], "stored_count"),
        selection_rule=_string(raw["selection_rule"], "selection_rule"),
    )


def _parse_column(raw: dict[str, JsonValue]) -> TableColumn:
    _exact(raw, {"name", "unit", "type"}, "column")
    try:
        type_ = TableValueType(_string(raw["type"], "column.type"))
        unit = None if raw["unit"] is None else Unit(_string(raw["unit"], "column.unit"))
    except ValueError as error:
        raise CharacterizationError("table_schema", "unknown table column enum") from error
    return TableColumn(name=_string(raw["name"], "column.name"), unit=unit, type=type_)


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CharacterizationError("table_schema", f"{label} must be object")
    return value


def _list(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise CharacterizationError("table_schema", f"{label} must be array")
    return value


def _string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CharacterizationError("table_schema", f"{label} must be nonempty string")
    return value


def _integer(value: JsonValue, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("table_schema", f"{label} must be integer")
    return value


def _exact(raw: Mapping[str, JsonValue], fields: set[str], label: str) -> None:
    if set(raw) != fields:
        raise CharacterizationError("table_schema", f"{label} fields do not match schema")
