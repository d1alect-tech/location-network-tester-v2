from __future__ import annotations

import json
from typing import TYPE_CHECKING

from lnt.analysis import analysis_to_payload, analyze_measurement_session, write_analysis
from lnt.simulate import simulate_session

if TYPE_CHECKING:
    from pathlib import Path


def test_analysis_schema_v2_reason_codes_input_reference_for_legacy_manifest(
    tmp_path: Path,
) -> None:
    # Given: a schema-v1 capture, which has no explicit CH1 transfer model.
    session = simulate_session(
        out_dir=tmp_path / "legacy",
        profile="bad",
        duration_s=2.1,
        sample_rate_hz=250_000.0,
        seed=6022,
    )

    # When: its analysis is materialized as the public metrics payload.
    payload = analysis_to_payload(analyze_measurement_session(session))

    # Then: v2 records that input referral is unavailable instead of guessing from front_end.
    assert payload["schema_version"] == 2
    assert payload["ch1_input_reference"] == {
        "status": "unavailable",
        "reason_code": "manifest_schema_v1",
        "model_kind": None,
        "baseline_session_id": None,
        "model": None,
        "qualification_rule_id": None,
        "qualified_bin_count": 0,
        "total_bin_count": 0,
        "corrected_peaks": [],
    }


def test_write_analysis_keeps_raw_spectrum_and_rewrites_unavailable_input_reference_csv(
    tmp_path: Path,
) -> None:
    # Given: a legacy analysis and a stale input-referred artifact from a prior run.
    session = simulate_session(
        out_dir=tmp_path / "legacy-artifacts",
        profile="quiet",
        duration_s=2.1,
        sample_rate_hz=250_000.0,
        seed=6022,
    )
    result = analyze_measurement_session(session)
    input_referred_path = session / "spectrum_input_referred.csv"
    input_referred_path.write_text("stale\n", encoding="utf-8")

    # When: analysis artifacts are written.
    metrics_path, raw_spectrum_path = write_analysis(session, result)

    # Then: the legacy scope-plane CSV is unchanged and the unavailable CSV is emptied/replaced.
    raw_lines = raw_spectrum_path.read_text(encoding="utf-8").splitlines()
    assert raw_spectrum_path.name == "spectrum.csv"
    assert raw_lines[0] == "frequency_hz,psd_v2_per_hz"
    assert len(raw_lines) - 1 == result.spectrum.frequencies_hz.size
    assert input_referred_path.read_text(encoding="utf-8") == (
        "frequency_hz,input_referred_excess_psd_v2_per_hz\n"
    )
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["ch1_input_reference"]["reason_code"] == "manifest_schema_v1"
