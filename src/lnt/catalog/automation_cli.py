"""CLI-контракты автоматизации каталога, контекста и профилей."""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from lnt.catalog.connection import catalog_path, open_catalog_reader
from lnt.catalog.query_models import CatalogFilters, SessionHealth
from lnt.catalog.query_repository import CatalogQueryRepository
from lnt.catalog.reconcile import catalog_status
from lnt.context.model import ContextSnapshot
from lnt.context.schema import context_to_mapping
from lnt.context.store import ContextStore, ContextUpdate
from lnt.errors import InputError
from lnt.profiles import ProfileStore, profile_to_json

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Mapping

    from lnt._manifest_json import JsonValue

MAX_PAGE_SIZE: Final = 200


def configure_automation_parsers(
    add_parser: Callable[[str], argparse.ArgumentParser],
) -> None:
    """Добавляет верхнеуровневые команды автоматизации."""
    sessions = add_parser("sessions")
    sessions.description = "Запросы каталога сессий"
    session_commands = sessions.add_subparsers(dest="sessions_command", required=True)
    listing = session_commands.add_parser("list")
    listing.add_argument("--health", choices=[item.value for item in SessionHealth])
    listing.add_argument("--session-type")
    listing.add_argument("--source")
    listing.add_argument("--profile")
    listing.add_argument("--label")
    listing.add_argument("--tag")
    listing.add_argument("--page-size", type=int, default=50)
    listing.add_argument("--json", action="store_true", dest="json_output")
    listing.set_defaults(handler=_sessions_list)

    context = add_parser("context")
    context.description = "Контекст сессии"
    context_commands = context.add_subparsers(dest="context_command", required=True)
    show = context_commands.add_parser("show")
    show.add_argument("session_id")
    show.add_argument("--json", action="store_true", dest="json_output")
    show.set_defaults(handler=_context_show)
    setting = context_commands.add_parser("set")
    setting.add_argument("session_id")
    setting.add_argument("--expected-revision", type=int, required=True)
    setting.add_argument("--tag", action="append", default=[])
    setting.add_argument("--notes")
    setting.set_defaults(handler=_context_set)

    profiles = add_parser("profiles")
    profiles.description = "Профили"
    profile_commands = profiles.add_subparsers(dest="profiles_command", required=True)
    for name, handler in (("list", _profiles_list), ("show", _profiles_show)):
        command = profile_commands.add_parser(name)
        if name == "show":
            command.add_argument("profile_id")
        command.add_argument("--json", action="store_true", dest="json_output")
        command.set_defaults(handler=handler)

    reindex = add_parser("reindex")
    reindex.description = "Статус переиндексации"
    reindex_commands = reindex.add_subparsers(dest="reindex_command", required=True)
    reindex_status = reindex_commands.add_parser("status")
    reindex_status.add_argument("--json", action="store_true", dest="json_output")
    reindex_status.set_defaults(handler=_reindex_status)


def _print(
    payload: Mapping[str, JsonValue],
    *,
    json_output: bool,
) -> None:
    if json_output:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        sys.stdout.write("; ".join(f"{key}: {value}" for key, value in payload.items()) + "\n")


def _session(args: argparse.Namespace) -> tuple[Path, str]:
    session_id = cast("str", args.session_id)
    with open_catalog_reader(catalog_path()) as connection:
        row = CatalogQueryRepository(connection).find(session_id)
    if row is None:
        raise InputError("сессия не найдена")
    return Path(row.storage_path), session_id


def _sessions_list(args: argparse.Namespace) -> int:
    health = cast("str | None", args.health)
    filters = CatalogFilters(
        health=None if health is None else SessionHealth(health),
        session_type=cast("str | None", args.session_type),
        source=cast("str | None", args.source),
        profile=cast("str | None", args.profile),
        label=cast("str | None", args.label),
        tag=cast("str | None", args.tag),
    )
    size = cast("int", args.page_size)
    if not 1 <= size <= MAX_PAGE_SIZE:
        raise InputError("page-size должен быть от 1 до 200")
    with open_catalog_reader(catalog_path()) as connection:
        page = CatalogQueryRepository(connection).page(filters, None, size)
    _print(
        {"items": [{"id": item.session_id, "health": item.health} for item in page.items]},
        json_output=cast("bool", args.json_output),
    )
    return 0


def _context_show(args: argparse.Namespace) -> int:
    directory, session_id = _session(args)
    snapshot = ContextStore(directory, session_id).load().snapshot or ContextSnapshot.empty(
        session_id
    )
    _print(context_to_mapping(snapshot), json_output=cast("bool", args.json_output))
    return 0


def _context_set(args: argparse.Namespace) -> int:
    directory, session_id = _session(args)
    store = ContextStore(directory, session_id)
    current = store.load().snapshot or ContextSnapshot.empty(session_id)
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    tags = tuple(cast("list[str]", args.tag)) or current.tags
    notes = cast("str | None", args.notes)
    snapshot = replace(
        current,
        revision=current.revision + 1,
        tags=tags,
        notes=current.notes if notes is None else notes,
    )
    store.update(
        ContextUpdate(
            expected_revision=cast("int", args.expected_revision),
            snapshot=snapshot,
            actor="lnt.cli",
            changed_keys=("tags", "notes"),
            occurred_at=now,
            event_id=uuid.uuid4().hex,
        )
    )
    sys.stdout.write(f"Контекст обновлён: revision {snapshot.revision}\n")
    return 0


def _profiles_list(args: argparse.Namespace) -> int:
    items = [json.loads(profile_to_json(item)) for item in ProfileStore().list()]
    _print({"items": items}, json_output=cast("bool", args.json_output))
    return 0


def _profiles_show(args: argparse.Namespace) -> int:
    payload = json.loads(profile_to_json(ProfileStore().get(cast("str", args.profile_id))))
    _print(payload, json_output=cast("bool", args.json_output))
    return 0


def _reindex_status(args: argparse.Namespace) -> int:
    status_payload = catalog_status(catalog_path())
    health: dict[str, JsonValue] = dict(status_payload["health"])
    last = status_payload["last_reconcile"]
    last_payload: dict[str, JsonValue] | None = (
        None
        if last is None
        else {
            "completed_utc": last["completed_utc"],
            "scanned": last["scanned"],
            "changed": last["changed"],
            "deleted": last["deleted"],
        }
    )
    _print(
        {
            "health": health,
            "last_reconcile": last_payload,
        },
        json_output=cast("bool", args.json_output),
    )
    return 0
