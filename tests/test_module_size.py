"""Политика размера модулей (Todo 51): ≤250 чистых LOC на производственный модуль.

Чистый LOC = непустые строки без строк-комментариев (``#`` для Python,
``//`` для JS/TS). Сгенерированные и вендорные деревья исключены явно:
``src/lnt/ui/static/v2`` (сборка Vite), ``static/vendor``, шрифты, а также
тесты и test-support фронтенда (``*.spec.ts``, ``testkit/``).

Модули из ``_GRANDFATHERED`` — восстановленное наследие и готовые экраны
Todo 44, у которых превышение зафиксировано точным значением: файл не может
вырасти дальше, а снятие ограничения возможно только реальным разбиением.
Любой НОВЫЙ модуль свыше лимита падает здесь же.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_ROOT: Final = Path(__file__).resolve().parent.parent
_LIMIT: Final = 250

# Точные значения пересчитываются тестом; запись означает «ровно столько сейчас».
_GRANDFATHERED: Final[dict[str, int]] = {
    # Очередь C4: cli.py разбит на cli_simulate/cli_capture/cli_compare
    # (compare читает metrics.json+spectrum.csv с откатом на analyze_session);
    # analysis.py разбит на analysis_types/payload/render/write, фасад тонкий.
    # Очередь C3: масштаб raw→В переехал в lnt.adc_calibration (единый источник
    # истины с поправкой); capture-сборка ужалась честным выделением.
    # Очередь A4: launcher.py ужался до 250 (канон в lnt.cli_spec) и снят с дедлайна.
    # Хвост C4 (расслоение _GRANDFATHERED-модулей) закрыт: _manifest_schema
    # (344→178) разбит на _manifest_primitives/_manifest_parse/_manifest_serialize,
    # acquire (300→214) — на acquire_setup/acquire_validation, runtime/store
    # (261→229) — на store_codecs/store_transitions, experiments/runner (257→227) —
    # на runner_errors/runner_mapping; все четыре ушли под 250 и сняты с дедлайна.
    # Фронтенд Todo 44 (замороженные экраны после visual-QA).
    # T11-доб: comparisonView (393→246), profileManager (305→154),
    # experimentsWorkspace (297→232), hypothesisView (284→100) и
    # trendView (255→227) разбиты и сняты с дедлайна.
    # T10-C2/C3: workbench (306→246) разбит на workbenchControls/inputReferencePanel,
    # spectrogramPanel (288→228) — на spectrogramLoader/WindowForm/Summary-CSV;
    # оба ушли под 250 и сняты с дедлайна.
    "frontend/src/components/charts/spectrogramView.ts": 269,
}

_PY_GLOBS: Final = ("src/lnt/**/*.py",)
_JS_GLOBS: Final = ("src/lnt/ui/static/*.js", "frontend/src/**/*.ts", "frontend/src/**/*.js")
_EXCLUDE_PARTS: Final = (
    "static/v2",
    "static/vendor",
    "__pycache__",
    "node_modules",
    "testkit",
)
_COMMENT_PREFIXES_PY: Final = "#"
_COMMENT_PREFIXES_JS: Final = "//"


def _is_excluded(path: Path) -> bool:
    posix = path.as_posix()
    return any(part in posix for part in _EXCLUDE_PARTS)


def _pure_loc(path: Path) -> int:
    prefix = _COMMENT_PREFIXES_PY if path.suffix == ".py" else _COMMENT_PREFIXES_JS
    return sum(
        bool(line.strip()) and not line.lstrip().startswith(prefix)
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def _production_files() -> list[Path]:
    files: list[Path] = []
    for pattern in (*_PY_GLOBS, *_JS_GLOBS):
        for path in sorted(_ROOT.glob(pattern)):
            if not path.is_file() or _is_excluded(path):
                continue
            if path.name.endswith((".spec.ts", ".test.ts", ".d.ts")):
                continue
            files.append(path)
    return files


def test_production_modules_respect_250_pure_loc_policy() -> None:
    offenders: list[str] = []
    seen_grandfathered: set[str] = set()
    for path in _production_files():
        relative = path.relative_to(_ROOT).as_posix()
        pure_loc = _pure_loc(path)
        if pure_loc <= _LIMIT:
            continue
        if relative in _GRANDFATHERED:
            seen_grandfathered.add(relative)
            assert pure_loc <= _GRANDFATHERED[relative], (
                f"{relative} вырос до {pure_loc} чистых LOC "
                f"(потолок дедлайна {relative}: {_GRANDFATHERED[relative]}); "
                "разбей модуль вместо роста"
            )
            continue
        offenders.append(f"{relative} = {pure_loc}")
    assert not offenders, "модули свыше 250 чистых LOC:\n" + "\n".join(offenders)


def test_grandfathered_entries_stay_used_and_measured() -> None:
    """Каждая запись дедлайна существует, превышает лимит и равна факту."""
    measured = {path.relative_to(_ROOT).as_posix(): _pure_loc(path) for path in _production_files()}
    for relative, recorded in _GRANDFATHERED.items():
        assert relative in measured, f"дедлайн указывает на отсутствующий файл: {relative}"
        assert measured[relative] > _LIMIT, (
            f"{relative} теперь {measured[relative]} LOC — убери запись из дедлайна"
        )
        assert measured[relative] == recorded, (
            f"{relative}: зафиксировано {recorded}, фактически {measured[relative]}; "
            "обнови значение только вместе с реальным разбиением"
        )


def test_generated_and_vendor_trees_are_out_of_policy_scope() -> None:
    """Явная проверка исключений: сборка Vite и вендор не участвуют в политике."""
    built = _ROOT / "src/lnt/ui/static/v2/assets"
    vendor = _ROOT / "src/lnt/ui/static/vendor"
    assert built.is_dir()
    assert vendor.is_dir()
    for path in (*built.glob("*.js"), *vendor.glob("*.js")):
        assert _is_excluded(path), f"сгенерированный/вендорный файл попал в политику: {path}"


def test_no_third_chart_library_sneaks_into_frontend_sources() -> None:
    """Смежный guard политики: Plotly запрещён в исходниках и статике."""
    pattern = re.compile(r"\bplotly\b", re.IGNORECASE)
    hits = [
        path.relative_to(_ROOT).as_posix()
        for path in _production_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not hits, f"Plotly обнаружен в: {hits}"
