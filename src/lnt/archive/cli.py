"""Argparse-поверхность checksum-verified архивов."""

from __future__ import annotations

import argparse  # noqa: TC003 - runtime parser
from pathlib import Path

from .export import ExportSelection, create_archive
from .inspect import inspect_archive
from .restore import restore_archive


def configure_archive_parser(archive: argparse.ArgumentParser) -> None:
    """Регистрирует ``lnt archive`` и четыре операции."""
    commands = archive.add_subparsers(dest="archive_command", required=True)

    create = commands.add_parser("create", help="создать архив явной выборки")
    create.add_argument("output", type=Path)
    create.add_argument("--root", type=Path, required=True, help="корень сессий")
    create.add_argument("--session", action="append", default=[])
    create.add_argument("--experiment", action="append", default=[])
    create.set_defaults(handler=_create)

    listing = commands.add_parser("list", help="показать manifest архива")
    listing.add_argument("archive", type=Path)
    listing.set_defaults(handler=_list)

    verify = commands.add_parser("verify", help="проверить schema, limits и SHA-256")
    verify.add_argument("archive", type=Path)
    verify.set_defaults(handler=_verify)

    restore = commands.add_parser("restore", help="восстановить в один новый каталог")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--dest", type=Path, required=True)
    restore.add_argument("--dry-run", action="store_true")
    restore.set_defaults(handler=_restore)


def _create(args: argparse.Namespace) -> int:
    manifest = create_archive(
        args.output,
        ExportSelection(
            root=args.root,
            session_ids=tuple(args.session),
            experiment_ids=tuple(args.experiment),
        ),
    )
    print(f"Архив создан: {args.output} ({len(manifest.entries)} файлов)")  # noqa: T201
    return 0


def _list(args: argparse.Namespace) -> int:
    plan = inspect_archive(args.archive)
    print(f"Версия архива: {plan.manifest.archive_schema_version}")  # noqa: T201
    print(f"Build ID: {plan.manifest.provenance.build_id}")  # noqa: T201
    for entry in plan.manifest.entries:
        print(f"{entry.size:>12}  {entry.sha256}  {entry.path}")  # noqa: T201
    return 0


def _verify(args: argparse.Namespace) -> int:
    plan = inspect_archive(args.archive)
    count = len(plan.manifest.entries)
    message = f"Архив проверен: {count} файлов, {plan.expanded_bytes} байт после распаковки"
    print(message)  # noqa: T201
    return 0


def _restore(args: argparse.Namespace) -> int:
    plan = restore_archive(args.archive, args.dest, dry_run=args.dry_run)
    prefix = "План восстановления" if args.dry_run else "Архив восстановлен"
    print(f"{prefix}: {args.dest} ({len(plan.manifest.entries)} файлов)")  # noqa: T201
    return 0
