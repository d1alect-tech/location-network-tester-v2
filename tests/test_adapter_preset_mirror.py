"""Дрейф-тест закреплённого зеркала пресета адаптера (TS ↔ Python).

Идиома как у ``tests/test_ui_chart_contract.py`` и ``tests/test_module_size.py``:
питон-тест читает текст фронтенд-модуля ``frontend/src/capture/adapterPreset.ts``
и сверяет литералы констант с ``lnt.ripple.adapter``. Зеркало правится только
руками, в паре с Python-источником (как corpus ↔ mockGolden); любое
расхождение литералов = RED.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from lnt.ripple.adapter import RIN_OHM, SETTLING_TAU_MULTIPLE, TOPOLOGY_ID, AdapterSpec

_ROOT: Final = Path(__file__).resolve().parent.parent
_PRESET_PATH: Final = _ROOT / "frontend" / "src" / "capture" / "adapterPreset.ts"


def _source() -> str:
    assert _PRESET_PATH.is_file(), f"нет закреплённого зеркала пресета: {_PRESET_PATH}"
    return _PRESET_PATH.read_text(encoding="utf-8")


def _number_literal(source: str, key: str) -> float:
    match = re.search(rf"{key}:\s*(?P<value>\d[\d_]*(?:\.\d+)?)", source)
    assert match is not None, f"adapterPreset.ts: нет числового литерала {key}"
    return float(match.group("value").replace("_", ""))


def _string_literal(source: str, key: str) -> str:
    match = re.search(rf'{key}:\s*"(?P<value>[^"]+)"', source)
    assert match is not None, f"adapterPreset.ts: нет строкового литерала {key}"
    return match.group("value")


def test_adapter_preset_literals_mirror_lnt_ripple_adapter() -> None:
    source = _source()
    adapter = AdapterSpec()
    assert _number_literal(source, "capNfNominal") == adapter.cap_nf
    assert _number_literal(source, "seriesROhmNominal") == adapter.series_r_ohm
    assert _number_literal(source, "probeMultiplier") == adapter.probe_multiplier
    assert _number_literal(source, "rinOhm") == RIN_OHM
    assert _number_literal(source, "settlingTauMultiple") == SETTLING_TAU_MULTIPLE
    assert _string_literal(source, "topologyId") == TOPOLOGY_ID


def test_adapter_preset_stays_local_offline_mirror() -> None:
    """H9: пресет закреплён во фронтенде, с бэкенда не приходит."""
    source = _source()
    assert not re.search(r"\bimport\b", source), "зеркало не импортирует: локальные константы"
    assert not re.search(r"\bfetch\b", source), "зеркало не ходит в сеть (H9, оффлайн-первый)"
