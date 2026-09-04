"""Проверка золотых вендорных пинов LNT (очередь A4).

Только чтение: сверяет зафиксированные значения с диском и манифестами,
ничего не скачивает и не меняет. Несоответствие — повод разбираться,
а не молча переписывать константы (золотые значения заморожены).

Проверяет: uPlot (размер и SHA-256 вендорных файлов, версия UPLOT_VERSION),
пин Hantek (коммит e65d52b в pyproject и dependency-manifest.json),
замороженные манифесты (записи dependency-manifest.json и хэши
fonts/manifest.json против файлов на диске).

Коды выхода: 0 — пины сошлись; 1 — расхождение; 2 — нечитаемый вход.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

_REPO_ROOT: Final = Path(__file__).resolve().parent.parent
UPLOT_VERSION: Final = "1.6.32"
UPLOT_ESM_REL: Final = Path("src/lnt/ui/static/vendor/uPlot.esm.js")
UPLOT_ESM_SIZE: Final = 145423
UPLOT_ESM_SHA256: Final = "5dd9b3281aa64b461b42d9945f6adb2649d346502b12281a9ae0d46599a80eba"
UPLOT_CSS_REL: Final = Path("src/lnt/ui/static/vendor/uPlot.min.css")
UPLOT_CSS_SIZE: Final = 1857
UPLOT_CSS_SHA256: Final = "df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04"
UPLOT_CHART_REL: Final = Path("src/lnt/ui/static/uplot-chart.js")
_VERSION_PATTERN: Final = re.compile(r'UPLOT_VERSION\s*=\s*"([^"]+)"')
HANTEK_COMMIT: Final = "e65d52b0f2536e56eaadbb555e5d7b756409c36e"
HANTEK_SHORT: Final = HANTEK_COMMIT[:7]
EXIT_OK: Final = 0
EXIT_MISMATCH: Final = 1
EXIT_MALFORMED: Final = 2


@dataclass(frozen=True, slots=True)
class _VendoredFile:
    """Золотой пин одного вендорного файла: путь, размер и SHA-256."""

    rel: Path
    size: int
    digest: str
    label: str


_UPLOT_FILES: Final = (
    _VendoredFile(UPLOT_ESM_REL, UPLOT_ESM_SIZE, UPLOT_ESM_SHA256, "uplot"),
    _VendoredFile(UPLOT_CSS_REL, UPLOT_CSS_SIZE, UPLOT_CSS_SHA256, "uplot"),
)


class _MalformedError(Exception):
    """Вход нечитаем: проверка останавливается до семантического сравнения."""


def _load_json(path: Path) -> object:
    """Читает JSON-файл, отображая любой сбой в типизированную ошибку."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"нечитаемый файл {path}: {exc}"
        raise _MalformedError(msg) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"битый JSON в {path}: {exc}"
        raise _MalformedError(msg) from exc


def _check_file(root: Path, spec: _VendoredFile, errors: list[str]) -> None:
    """Сверяет размер и SHA-256 вендорного файла с золотыми значениями."""
    try:
        data = (root / spec.rel).read_bytes()
    except OSError as exc:
        errors.append(f"{spec.label}: файл недоступен: {spec.rel} ({exc})")
        return
    if len(data) != spec.size:
        errors.append(
            f"{spec.label}: размер {len(data)} != золотой {spec.size}: {spec.rel.as_posix()}",
        )
    if hashlib.sha256(data).hexdigest() != spec.digest:
        errors.append(f"{spec.label}: sha256 не сошёлся с золотым: {spec.rel.as_posix()}")


def _check_uplot_version(root: Path, errors: list[str]) -> None:
    """Сверяет константу UPLOT_VERSION в uplot-chart.js с золотым пином."""
    try:
        text = (root / UPLOT_CHART_REL).read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"uplot: файл недоступен: {UPLOT_CHART_REL.as_posix()} ({exc})")
        return
    match = _VERSION_PATTERN.search(text)
    if match is None:
        errors.append(f"uplot: UPLOT_VERSION не найдена в {UPLOT_CHART_REL.as_posix()}")
    elif match.group(1) != UPLOT_VERSION:
        errors.append(f"uplot: версия {match.group(1)} != золотая {UPLOT_VERSION}")


def _manifest_by_name(root: Path) -> dict[str, dict[str, str]]:
    """Индекс записей dependency-manifest.json по имени компонента."""
    raw = _load_json(root / "dependency-manifest.json")
    if not isinstance(raw, list):
        raise _MalformedError("dependency-manifest.json: верхний уровень обязан быть массивом")
    by_name: dict[str, dict[str, str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        version = item.get("version")
        digest = item.get("hash")
        by_name[name] = {
            "version": version if isinstance(version, str) else "",
            "hash": digest if isinstance(digest, str) else "",
        }
    return by_name


def _check_manifest_pins(root: Path, errors: list[str]) -> None:
    """Сверяет записи uplot и hantek в dependency-manifest.json с золотом."""
    by_name = _manifest_by_name(root)
    uplot = by_name.get("uplot")
    if uplot is None:
        errors.append("dependency-manifest.json: нет записи 'uplot'")
    else:
        if uplot["version"] != UPLOT_VERSION:
            errors.append(
                f"dependency-manifest.json: uplot {uplot['version']} != {UPLOT_VERSION}",
            )
        if uplot["hash"] != f"sha256:{UPLOT_ESM_SHA256}":
            errors.append("dependency-manifest.json: хэш uplot отличается от золотого")
    hantek = by_name.get("hantek6022api")
    if hantek is None:
        errors.append("dependency-manifest.json: нет записи 'hantek6022api'")
    elif hantek["hash"] != f"git-commit:{HANTEK_COMMIT}":
        errors.append("dependency-manifest.json: пин hantek отличается от золотого")


def _check_pyproject(root: Path, errors: list[str]) -> None:
    """Проверяет, что pyproject сохраняет пин Hantek на золотой коммит."""
    try:
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"pyproject.toml недоступен: {exc}")
        return
    if HANTEK_SHORT not in text:
        errors.append(f"pyproject.toml: пин hantek {HANTEK_SHORT} отсутствует")


def _check_fonts_manifest(root: Path, errors: list[str]) -> None:
    """Пересчитывает хэши WOFF2 с диска против замороженного манифеста."""
    raw = _load_json(root / "src/lnt/ui/static/fonts/manifest.json")
    if not isinstance(raw, dict):
        raise _MalformedError("fonts/manifest.json: верхний уровень обязан быть объектом")
    files = raw.get("files")
    if not isinstance(files, dict):
        raise _MalformedError("fonts/manifest.json: поле 'files' обязано быть объектом")
    font_dir = root / "src/lnt/ui/static/fonts"
    for name, expected in files.items():
        if not isinstance(name, str) or not isinstance(expected, str):
            raise _MalformedError("fonts/manifest.json: запись обязана быть строковой парой")
        try:
            actual = hashlib.sha256((font_dir / name).read_bytes()).hexdigest()
        except OSError:
            errors.append(f"fonts: файл отсутствует на диске: {name}")
            continue
        if actual != expected:
            errors.append(f"fonts: хэш {name} отличается от замороженного манифеста")


def verify(root: Path) -> dict[str, object]:
    """Прогоняет все проверки пинов и возвращает вердикт."""
    errors: list[str] = []
    try:
        for spec in _UPLOT_FILES:
            _check_file(root, spec, errors)
        _check_uplot_version(root, errors)
        _check_manifest_pins(root, errors)
        _check_pyproject(root, errors)
        _check_fonts_manifest(root, errors)
    except _MalformedError as exc:
        return {"ok": False, "errors": [str(exc)], "malformed": True, "checked": 0}
    return {
        "ok": not errors,
        "errors": sorted(errors),
        "malformed": False,
        "checked": 6,
    }


def main(argv: list[str] | None = None) -> int:
    """Точка входа: разбирает аргументы, проверяет пины, возвращает код выхода."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(_REPO_ROOT), help="корень репозитория")
    args = parser.parse_args(argv)
    verdict = verify(Path(args.root))
    errors = cast("list[str]", verdict["errors"])
    for error in errors:
        sys.stderr.write(f"PIN_VENDOR ERROR: {error}\n")
    if verdict["malformed"]:
        sys.stderr.write("PIN_VENDOR EXIT_CODE=2\n")
        return EXIT_MALFORMED
    code = EXIT_OK if verdict["ok"] else EXIT_MISMATCH
    sys.stderr.write(f"PIN_VENDOR EXIT_CODE={code}\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
