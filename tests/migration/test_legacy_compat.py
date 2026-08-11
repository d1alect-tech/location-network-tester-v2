from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from lnt.analysis import AnalysisResult, analysis_to_payload, analyze_session
from lnt.catalog.connection import open_catalog_reader
from lnt.catalog.reconcile import reconcile_catalog
from lnt.manifest import manifest_from_json
from lnt.simulate import simulate_session

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "manifest_frozen"
LEGACY_MANIFEST = FIXTURE_ROOT / "schema_v1_synthetic_legacy.json"


def test_v1_manifest_read_preserves_legacy_contract() -> None:
    # Given
    text = LEGACY_MANIFEST.read_text(encoding="utf-8")

    # When
    manifest = manifest_from_json(text)

    # Then
    assert manifest.schema_version == 1
    assert manifest.session_id == "frozen-v1-synthetic"
    assert manifest.ch1_setup is None


def test_legacy_metrics_recompute_with_documented_tolerance(tmp_path: Path) -> None:
    # Given
    session = simulate_session(
        out_dir=tmp_path / "legacy",
        profile="quiet",
        duration_s=2.4,
        sample_rate_hz=20_000.0,
        seed=50,
    )
    stored_result = analyze_session(session)
    assert isinstance(stored_result, AnalysisResult)
    stored = analysis_to_payload(stored_result)

    # When
    recomputed_result = analyze_session(session)
    assert isinstance(recomputed_result, AnalysisResult)
    recomputed = analysis_to_payload(recomputed_result)

    # Then
    stored_needle = stored["needle"]
    recomputed_needle = recomputed["needle"]
    assert isinstance(stored_needle, dict)
    assert isinstance(recomputed_needle, dict)
    for name in ("needle_mean_v", "needle_sigma_ratio"):
        assert recomputed_needle[name] == pytest.approx(stored_needle[name], rel=1e-9, abs=0.0)
    assert recomputed["spectrum"] == stored["spectrum"]


def test_corrupt_copies_remain_visible_with_health_codes(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    root.mkdir()
    byte_flip = root / "byte-flip"
    byte_flip.mkdir()
    payload = json.loads(LEGACY_MANIFEST.read_text(encoding="utf-8"))
    payload["session_id"] = "byte-flip"
    (byte_flip / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    np.save(byte_flip / "ch1.npy", np.zeros(4, dtype=np.float32))
    with (byte_flip / "ch1.npy").open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"\x01")
    truncated = root / "truncated-manifest"
    truncated.mkdir()
    (truncated / "manifest.json").write_text('{"schema_version":', encoding="utf-8")
    database = tmp_path / "catalog.sqlite3"

    # When
    reconcile_catalog(root, database, rebuild=True)

    # Then
    with open_catalog_reader(database) as connection:
        rows = connection.execute(
            "SELECT storage_path, health FROM catalog_sessions ORDER BY storage_path"
        ).fetchall()
    assert [(Path(row[0]).name, row[1]) for row in rows] == [
        ("byte-flip", "ok"),
        ("truncated-manifest", "corrupt_manifest"),
    ]


def test_schema_v1_never_fabricates_input_reference(tmp_path: Path) -> None:
    # Given
    session = simulate_session(
        out_dir=tmp_path / "legacy",
        profile="quiet",
        duration_s=2.4,
        sample_rate_hz=20_000.0,
        seed=51,
    )

    # When
    result = analyze_session(session)
    assert isinstance(result, AnalysisResult)
    payload = analysis_to_payload(result)

    # Then
    correction = payload["ch1_input_reference"]
    assert isinstance(correction, dict)
    assert correction["status"] == "unavailable"
    assert correction["reason_code"] == "manifest_schema_v1"
    assert correction["model"] is None
    assert correction["corrected_peaks"] == []
