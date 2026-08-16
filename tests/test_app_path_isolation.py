from __future__ import annotations

import json
from pathlib import Path

from lnt.catalog.connection import catalog_path, open_catalog_reader
from lnt.session_projection import index_session

REAL_CATALOG = Path.home() / "AppData" / "Local" / "LNT" / "catalog.sqlite3"


def test_index_session_without_explicit_path_stays_out_of_real_appdata(tmp_path: Path) -> None:
    before = REAL_CATALOG.read_bytes() if REAL_CATALOG.exists() else None
    session = tmp_path / "sessions" / "isolated-session"
    session.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "session_id": "isolated-session",
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
    }
    (session / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (session / "ch1.npy").write_bytes(b"fixture")

    index_session(session)

    isolated_catalog = catalog_path()
    assert isolated_catalog.is_relative_to(tmp_path)
    with open_catalog_reader(isolated_catalog) as connection:
        assert (
            connection.execute(
                "SELECT session_id FROM catalog_sessions WHERE session_id='isolated-session'"
            ).fetchone()
            is not None
        )
    after = REAL_CATALOG.read_bytes() if REAL_CATALOG.exists() else None
    assert after == before
