"""Детерминированные CSV-таблицы численных результатов."""

import csv
import io
from collections.abc import Iterable
from typing import NamedTuple

from lnt.reporting.models import EstimandResult, ReportSchema1


class CsvTable(NamedTuple):
    """Имя и строки одной CSV-таблицы."""

    name: str
    header: tuple[str, ...]
    rows: Iterable[tuple[str | int | float, ...]]


def _write(table: CsvTable) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(table.header)
    writer.writerows(table.rows)
    return stream.getvalue()


def _estimand_rows(
    category: str,
    results: tuple[EstimandResult, ...],
) -> Iterable[tuple[str | int | float, ...]]:
    for index, result in enumerate(results, start=1):
        interval_low = "" if result.interval is None else result.interval.low
        interval_high = "" if result.interval is None else result.interval.high
        yield (
            category,
            index,
            "effect",
            result.metadata.estimator_name,
            result.metadata.sampling_unit,
            result.metadata.n,
            result.mean_effect,
            result.median_effect,
            result.robust_effect,
            interval_low,
            interval_high,
        )


def render_csv_tables(report: ReportSchema1) -> dict[str, str]:
    """Рендерит таблицы, где каждая численная строка несёт unit, estimator и N."""
    estimands = tuple(_estimand_rows("primary", report.primary_estimands)) + tuple(
        _estimand_rows("secondary", report.secondary_estimands)
    )
    plane_rows = (
        (
            plane.kind.value,
            plane.available,
            plane.reason_code or "",
            plane.session_id,
            plane.member_id,
            plane.unit,
            plane.estimator,
            plane.n,
            len(plane.values),
        )
        for plane in report.planes
    )
    event = report.events_summary
    event_rows = (
        ()
        if event is None
        else (
            ("candidates", event.unit, event.estimator, event.n, event.candidate_count),
            ("qualified", event.unit, event.estimator, event.n, event.qualified_count),
            ("unqualified_gaps", event.unit, event.estimator, event.n, event.unqualified_gap_count),
        )
    )
    tables = (
        CsvTable(
            "estimands.csv",
            (
                "category",
                "result_index",
                "unit",
                "estimator",
                "sampling_unit",
                "n",
                "mean",
                "median",
                "robust",
                "interval_low",
                "interval_high",
            ),
            estimands,
        ),
        CsvTable(
            "events.csv",
            ("metric", "unit", "estimator", "n", "value"),
            event_rows,
        ),
        CsvTable(
            "planes.csv",
            (
                "plane",
                "available",
                "reason_code",
                "session_id",
                "member_id",
                "unit",
                "estimator",
                "n",
                "result_count",
            ),
            plane_rows,
        ),
    )
    return {table.name: _write(table) for table in tables}
