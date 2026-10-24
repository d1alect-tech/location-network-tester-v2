"""Пин синхронизации ripple-мануала с фактическим CLI (N9, GAP-7).

Мануал это операторский контракт: режим декларации адаптера, дефолты
адаптерных флагов и примеры stderr обязаны совпадать с кодом CLI, а не
с памятью автора документации.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from lnt._cli_ripple import configure_ripple_parser
from lnt._cli_ripple_declaration import resolve_adapter
from lnt.errors import InputError
from lnt.ripple.adapter_declaration import AdapterDeclaration
from lnt.types import ComponentValuesBasis

_MANUAL = Path(__file__).parents[1] / "docs" / "ripple-measurement-ru.md"
_DECLARATION = AdapterDeclaration(
    cap_nf=100.0,
    series_r_ohm=0.0,
    preconnected=False,
    component_values_basis=ComponentValuesBasis.NOMINAL,
)


def _manual() -> str:
    return _MANUAL.read_text(encoding="utf-8")


def _flag_defaults() -> dict[str, str]:
    """Колонка «По умолчанию» таблицы флагов §6.2, по имени флага."""
    defaults: dict[str, str] = {}
    for line in _manual().splitlines():
        stripped = line.strip()
        if not stripped.startswith("| `--"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        defaults[cells[0].split()[0].strip("`")] = cells[-1]
    return defaults


def test_s61_premise_names_capture_mode_and_write_once_declaration() -> None:
    section = _manual().split("### 6.1")[1].split("### 6.2")[0]
    assert "не имеет отдельного поля" not in section
    for anchor in ("«Риппл-измерение»", "context.json", "lnt.capture", "write-once"):
        assert anchor in section, anchor


def test_s61_policy_core_survives_manifest_substitution_ban() -> None:
    section = _manual().split("### 6.1")[1].split("### 6.2")[0]
    for anchor in ("manifest.json", "RC-фронтенда", "провенанс"):
        assert anchor in section, anchor


def test_s62_adapter_flag_defaults_read_session_declaration() -> None:
    defaults = _flag_defaults()
    assert defaults["--cap-nf"] == "из декларации контекста сессии, иначе 100"
    assert defaults["--series-r-ohm"] == "из декларации контекста сессии, иначе 0"
    assert defaults["--probe"] == "из декларации контекста сессии, иначе `1x`"
    assert defaults["--preconnected"] == "из декларации контекста сессии, иначе выключен"


def test_s62_conflicting_flag_is_typed_refusal_exit_2() -> None:
    section = _manual().split("### 6.2")[1].split("### 6.3")[0]
    assert "типизированным отказом с кодом 2" in section


def test_exit_code_2_row_lists_adapter_declaration_conflict() -> None:
    assert "флаг адаптера противоречит декларации контекста сессии" in _manual()


def test_stderr_example_matches_cli_mismatch_error_verbatim() -> None:
    args = argparse.Namespace(cap_nf=220.0, series_r_ohm=None, probe=None, preconnected=None)
    with pytest.raises(InputError) as excinfo:
        resolve_adapter(args, _DECLARATION)
    assert f"Ошибка: {excinfo.value}" in _manual()


def test_flag_table_and_defaults_match_cli_help() -> None:
    parser = argparse.ArgumentParser(prog="lnt ripple")
    configure_ripple_parser(parser, finite_float=float)
    help_text = " ".join(parser.format_help().split())
    for flag in _flag_defaults():
        assert flag in help_text, flag
    for fragment in (
        "из декларации контекста сессии, иначе 100 нФ",
        "из декларации контекста сессии, иначе 0 Ом",
        "из декларации контекста сессии, иначе 1x",
    ):
        assert fragment in help_text, fragment
