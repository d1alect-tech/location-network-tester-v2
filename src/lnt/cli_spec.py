"""Единый источник верхнеуровневых CLI-подкоманд LNT (очередь A4).

Каноническое множество имён subparsers из ``lnt.cli._build_parser``.
``lnt.launcher`` реэкспортирует его для диспетча замороженного exe, а паритет
с реальным парсером охраняют тесты ``test_gui_main_cli_subcommands_match_parser``
и ``tests/test_cli_spec.py``. Менять только вместе с CLI-поверхностью
(сейчас поверхность заморожена).
"""

from __future__ import annotations

from typing import Final

CLI_SUBCOMMANDS: Final = frozenset(
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
