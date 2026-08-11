"""Явная файловая граница для готовых report artifacts."""

from pathlib import Path

from lnt.reporting.csv_renderer import render_csv_tables
from lnt.reporting.html_renderer import render_html
from lnt.reporting.json_renderer import canonical_json
from lnt.reporting.models import ReportSchema1


def write_report(report: ReportSchema1, directory: Path) -> tuple[Path, ...]:
    """Записывает canonical JSON, CSV и offline HTML в заданный каталог."""
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    html_path = directory / "report.html"
    json_path.write_bytes(canonical_json(report))
    html_path.write_text(render_html(report), encoding="utf-8", newline="\n")
    csv_paths: list[Path] = []
    for name, content in render_csv_tables(report).items():
        path = directory / name
        path.write_text(content, encoding="utf-8", newline="\n")
        csv_paths.append(path)
    return (json_path, html_path, *csv_paths)
