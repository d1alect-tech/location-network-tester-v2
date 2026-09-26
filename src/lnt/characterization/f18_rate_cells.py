"""F18: чтение rate-зависимых ячеек сохранённой metadata-таблицы."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError

if TYPE_CHECKING:
    from lnt.characterization.tables import TableBlock

__all__ = ["persisted_analysis_rate_hz", "persisted_segment_samples"]

_ROW_COUNT: Final = 1


def persisted_segment_samples(table: TableBlock) -> int:
    """Прочитать выведенный движком сегмент из сохранённой metadata-таблицы.

    Число отсчётов зависит от частоты записи, поэтому decoder не может вывести
    его заново: единственный носитель — сохранённая ячейка, и читается она ДО
    locked-сверки таблицы, чтобы та сверяла все 72 объявленные ячейки, а не
    подменяла эту.
    """
    value = _persisted_rate_cell(table, "segment_samples")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CharacterizationError(
            "status_invariant", "F18 persisted segment is not an integer count"
        )
    return value


def persisted_analysis_rate_hz(table: TableBlock) -> float:
    """Прочитать измеренную частоту анализа из сохранённой metadata-таблицы.

    Вывести её из сегмента нельзя: round(0.001 * fs) обратим не для всякой fs, а
    артефакт хранит ровно ту частоту, на которой считались кадры.
    """
    value = _persisted_rate_cell(table, "analysis_rate_hz")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not float(value) > 0.0:
        raise CharacterizationError(
            "status_invariant", "F18 persisted analysis rate is not a positive number"
        )
    return float(value)


def _persisted_rate_cell(table: TableBlock, name: str) -> object:
    """Прочитать rate-зависимую ячейку по имени, не полагаясь на её позицию."""
    index = next(
        (position for position, column in enumerate(table.columns) if column.name == name),
        -1,
    )
    if index < 0 or table.row_count != _ROW_COUNT:
        raise CharacterizationError("status_invariant", f"F18 persisted {name} cell is absent")
    return table.rows[0][index]
