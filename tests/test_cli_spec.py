"""Паритет единого источника CLI-подкоманд (очередь A4)."""

from __future__ import annotations

import argparse
from typing import Final

from lnt import launcher
from lnt.cli import _build_parser  # pyright: ignore[reportPrivateUsage]
from lnt.cli_spec import CLI_SUBCOMMANDS

_FROZEN_SURFACE: Final = frozenset(
    {
        "analyze",
        "archive",
        "capture",
        "catalog",
        "compare",
        "context",
        "experiment",
        "hypothesis",
        "profiles",
        "reindex",
        "selftest",
        "sessions",
        "simulate",
        "support-bundle",
        "ui",
    }
)


def _parser_choices() -> set[str]:
    for action in _build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):  # pyright: ignore[reportPrivateUsage]
            return set(action.choices)
    raise AssertionError("у lnt.cli нет subparsers")


def test_cli_spec_matches_parser() -> None:
    assert set(CLI_SUBCOMMANDS) == _parser_choices()


def test_launcher_reexports_single_source() -> None:
    assert launcher.CLI_SUBCOMMANDS is CLI_SUBCOMMANDS


def test_cli_surface_stays_frozen() -> None:
    assert set(CLI_SUBCOMMANDS) == set(_FROZEN_SURFACE)
