"""Практический бюджет инкрементальной сверки 10 000 сессий."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from lnt.catalog.reconcile import reconcile_catalog

if TYPE_CHECKING:
    from pathlib import Path

SESSION_COUNT = 10_000
FULL_BUDGET_S = 90.0
INCREMENTAL_BUDGET_S = 8.0


def _manifest(index: int) -> str:
    session_id = f"perf-{index:05d}"
    return json.dumps(
        {
            "schema_version": 1,
            "session_id": session_id,
            "created_utc": "2026-08-11T12:00:00Z",
            "completed_utc": "2026-08-11T12:00:01Z",
            "source": "synthetic",
            "session_type": "measurement",
            "sample_rate_hz": 1.0,
            "duration_s": 1.0,
            "sample_count": 1,
            "line_frequency_hz": 50.0,
            "profile": "quiet",
            "baseline_session": None,
            "parameters": {},
            "ch1": {
                "filename": "ch1.npy",
                "role": "hf_probe",
                "unit": "V",
                "front_end": "fixture",
                "range_code": 1,
                "probe_multiplier": 1.0,
            },
            "ch2": None,
            "acquisition_telemetry": None,
            "synthetic_truth": None,
        },
        separators=(",", ":"),
    )


def test_ten_thousand_session_incremental_reconcile_meets_budget(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    root.mkdir()
    for index in range(SESSION_COUNT):
        session = root / f"session-{index:05d}"
        session.mkdir()
        (session / "manifest.json").write_text(_manifest(index), encoding="utf-8")

    # When
    started = time.perf_counter()
    full = reconcile_catalog(root, database)
    full_s = time.perf_counter() - started
    started = time.perf_counter()
    incremental = reconcile_catalog(root, database)
    incremental_s = time.perf_counter() - started
    # Then
    assert (full.inserted, incremental.skipped) == (SESSION_COUNT, SESSION_COUNT)
    assert full_s < FULL_BUDGET_S
    assert incremental_s < INCREMENTAL_BUDGET_S
