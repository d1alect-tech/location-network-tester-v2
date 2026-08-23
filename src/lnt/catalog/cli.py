"""Подкоманды CLI для обслуживания перестраиваемого каталога."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from lnt.catalog.connection import catalog_path
from lnt.catalog.reconcile import catalog_status, reconcile_catalog, verify_catalog
from lnt.errors import InputError

if TYPE_CHECKING:
    import argparse

    from lnt.catalog.reconcile_models import ReconcileResult


class ImportContextResult(TypedDict):
    """Результат безопасного просмотра legacy sidecar."""

    session_dir: str
    source: str
    would_import: bool
    dry_run: bool


def _database(command: argparse.ArgumentParser) -> None:
    command.add_argument("--database", type=Path, default=catalog_path())


def _root(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", type=Path, required=True, help="корень сессий")


def _json_flag(command: argparse.ArgumentParser) -> None:
    command.add_argument("--json", action="store_true", dest="json_output")


def configure_catalog_parser(catalog: argparse.ArgumentParser) -> None:
    """Настраивает уже добавленную группу ``catalog``."""
    commands = catalog.add_subparsers(dest="catalog_command", required=True)

    status = commands.add_parser("status", help="состояние и health-счётчики")
    _database(status)
    _json_flag(status)
    status.set_defaults(handler=_cmd_status)

    reindex = commands.add_parser("reindex", help="полностью перестроить проекции")
    _root(reindex)
    _database(reindex)
    _json_flag(reindex)
    reindex.set_defaults(handler=_cmd_reindex)

    verify = commands.add_parser("verify", help="проверить drift без записи")
    _root(verify)
    _database(verify)
    verify.add_argument(
        "--deep",
        action="store_true",
        help="хешировать содержимое raw-файлов (медленнее, ловит смену байтов)",
    )
    _json_flag(verify)
    verify.set_defaults(handler=_cmd_verify)

    import_context = commands.add_parser(
        "import-context",
        help="просмотреть импорт legacy context sidecar",
    )
    import_context.add_argument("session_dir", type=Path)
    import_context.add_argument("--dry-run", action="store_true", required=True)
    _json_flag(import_context)
    import_context.set_defaults(handler=_cmd_import_context)


def _print(payload: dict[str, int] | ImportContextResult, *, json_output: bool) -> None:
    if json_output:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return
    sys.stdout.write("; ".join(f"{key}: {value}" for key, value in payload.items()) + "\n")


def _result_payload(result: ReconcileResult) -> dict[str, int]:
    return {
        "scanned": result.scanned,
        "inserted": result.inserted,
        "updated": result.updated,
        "skipped": result.skipped,
        "deleted": result.deleted,
    }


def _cmd_reindex(args: argparse.Namespace) -> int:
    result = reconcile_catalog(
        cast("Path", args.root),
        cast("Path", args.database),
        rebuild=True,
    )
    _print(_result_payload(result), json_output=cast("bool", args.json_output))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    payload = catalog_status(cast("Path", args.database))
    if cast("bool", args.json_output):
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        counts = ", ".join(f"{health}={count}" for health, count in payload["health"].items())
        sys.stdout.write(f"Здоровье каталога: {counts or 'нет сессий'}\n")
        sys.stdout.write(f"Последняя сверка: {payload['last_reconcile'] or 'не выполнялась'}\n")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    deep = cast("bool", getattr(args, "deep", False))
    result = verify_catalog(
        cast("Path", args.root),
        cast("Path", args.database),
        deep=deep,
    )
    payload: dict[str, object] = {"drift_paths": list(result.drift_paths)}
    if deep:
        payload["baseline_created"] = result.baseline_created
    if cast("bool", args.json_output):
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    elif result.drift_paths:
        lines = "\n".join(f"- {path}" for path in result.drift_paths)
        sys.stdout.write(f"Обнаружено расхождение каталога:\n{lines}\n")
    elif result.baseline_created:
        sys.stdout.write("Создан базовый снимок содержимого; расхождений нет\n")
    else:
        sys.stdout.write("Расхождений каталога нет\n")
    return 1 if result.drift_paths else 0


def _cmd_import_context(args: argparse.Namespace) -> int:
    directory = cast("Path", args.session_dir)
    source = directory / "context.legacy.json"
    if not directory.is_dir() or directory.is_symlink():
        raise InputError("import-context: требуется обычный каталог скопированной fixture")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError("import-context: context.legacy.json не найден") from error
    except (json.JSONDecodeError, UnicodeError, OSError) as error:
        raise InputError("import-context: legacy sidecar повреждён") from error
    would_import = isinstance(payload, dict)
    result = ImportContextResult(
        session_dir=str(directory.resolve()),
        source=str(source.resolve()),
        would_import=would_import,
        dry_run=True,
    )
    _print(result, json_output=cast("bool", args.json_output))
    return 0
