"""T11: синтетическая truth-валидация перекрёстных помех CM/DM и полный конвейер."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.cli import EXIT_OK, main
from lnt.cm_dm.analysis import analyze_cm_dm_session
from lnt.ui.operations import LntBackend
from tests.cm_dm_fixtures import build_probe_pair_session

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.cm_dm.analysis import CmDmAnalysis

_CSV_HEADER = "frequency_hz,cm_psd_v2_per_hz,dm_psd_v2_per_hz,coherence"
_CROSSTALK_FLOOR_DB = -20.0
_GAIN_IMPROVEMENT_MIN_DB = 10.0
_DM_TONE_HZ = 100_000.0
_CM_TONE_HZ = 300_000.0
_CALIBRATION_PARAMS: dict[str, float] = {
    "probe_pair_correction_factor": 1.25,
    "probe_pair_gain_ratio": 0.8,
    "probe_pair_rejection_depth_db": 14.0,
}


def _crosstalk_db(result: CmDmAnalysis, reference_mode: str, tone_hz: float) -> float:
    """Чужая мода относительно опорной на бине tone_hz, дБ (минус — подавление)."""
    index = int(np.argmin(np.abs(result.band.frequency_hz - tone_hz)))
    if reference_mode == "cm":
        reference, other = result.band.cm_psd, result.band.dm_psd
    else:
        reference, other = result.band.dm_psd, result.band.cm_psd
    return 10.0 * math.log10(float(other[index]) / float(reference[index]))


def test_dm_only_injection_leaves_cm_quiet(tmp_path: Path) -> None:
    # Given: a purely differential synthetic pair, no common-mode content.
    session = build_probe_pair_session(tmp_path / "dm-only", probe_pair_kind="dm_only")

    # When: the session is analyzed.
    result = analyze_cm_dm_session(session)

    # Then: the DM tone dominates the peaks at its injected frequency.
    assert result.peaks[0].mode == "dm"
    assert result.peaks[0].frequency_hz == pytest.approx(_DM_TONE_HZ, rel=0.01)
    # And: at the DM tone bin the CM PSD is suppressed by at least 20 dB.
    assert _crosstalk_db(result, "dm", _DM_TONE_HZ) <= _CROSSTALK_FLOOR_DB


def test_cm_only_injection_leaves_dm_quiet(tmp_path: Path) -> None:
    # Given: a purely common-mode synthetic pair, no differential content.
    session = build_probe_pair_session(
        tmp_path / "cm-only",
        cm_tone_hz=_CM_TONE_HZ,
        probe_pair_kind="cm_only",
    )

    # When: the session is analyzed.
    result = analyze_cm_dm_session(session)

    # Then: the CM tone dominates the peaks at its injected frequency.
    assert result.peaks[0].mode == "cm"
    assert result.peaks[0].frequency_hz == pytest.approx(_CM_TONE_HZ, rel=0.01)
    # And: at the CM tone bin the DM PSD is suppressed by at least 20 dB.
    assert _crosstalk_db(result, "cm", _CM_TONE_HZ) <= _CROSSTALK_FLOOR_DB


def test_gain_correction_recovers_differential_pair(tmp_path: Path) -> None:
    # Given: two identical mistuned (gain=0.8) differential records, one
    # carrying published probe-pair calibration scalars in its parameters.
    corrected = build_probe_pair_session(
        tmp_path / "corrected",
        gain=0.8,
        probe_pair_kind="dm_only",
        calibration_params=_CALIBRATION_PARAMS,
        noise_sigma_v=1e-5,
    )
    uncorrected = build_probe_pair_session(
        tmp_path / "uncorrected",
        gain=0.8,
        probe_pair_kind="dm_only",
        noise_sigma_v=1e-5,
    )

    # When: both sessions are analyzed.
    corrected_result = analyze_cm_dm_session(corrected)
    uncorrected_result = analyze_cm_dm_session(uncorrected)

    # Then: calibration is picked up and the DM tone dominates the spectrum.
    assert corrected_result.status == "ok"
    assert corrected_result.calibration is not None
    assert corrected_result.calibration.gain_ratio_epsilon == pytest.approx(0.8)
    assert corrected_result.peaks[0].mode == "dm"
    # And: correction restores rejection — cleared floor and materially better
    # than the same record analyzed without calibration parameters.
    corrected_db = _crosstalk_db(corrected_result, "dm", _DM_TONE_HZ)
    uncorrected_db = _crosstalk_db(uncorrected_result, "dm", _DM_TONE_HZ)
    assert corrected_db <= _CROSSTALK_FLOOR_DB
    assert uncorrected_db - corrected_db >= _GAIN_IMPROVEMENT_MIN_DB


def test_full_pipeline_backend_to_artifacts(tmp_path: Path) -> None:
    # Given: a calibrated probe-pair session on disk.
    session = build_probe_pair_session(
        tmp_path / "backend",
        duration_s=0.05,
        calibration_params=_CALIBRATION_PARAMS,
    )

    # When: the panel backend analyzes it and writes artifacts.
    result = LntBackend().analyze_and_write(session)

    # Then: metrics.json parses with the canonical key set and an ok cm_dm
    # section carrying at most eight attributed peaks.
    assert result.session_type.value == "cm_dm"
    payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
    assert set(payload) == {
        "schema_version",
        "session_id",
        "profile",
        "source",
        "session_type",
        "sample_rate_hz",
        "duration_s",
        "needle",
        "line_quality",
        "spectrum",
        "ch1_input_reference",
        "cm_dm",
    }
    section = payload["cm_dm"]
    assert section["status"] == "ok"
    assert 1 <= len(section["peaks"]) <= 8
    # And: the band CSV artifact exists with the exact contract header.
    lines = (session / "cm_dm_spectrum.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == _CSV_HEADER


def test_full_pipeline_cli_parity(tmp_path: Path) -> None:
    # Given: two identically synthesized calibrated sessions, one routed
    # through the panel backend and one through the CLI analyze command.
    backend_session = build_probe_pair_session(
        tmp_path / "parity-backend",
        duration_s=0.05,
        calibration_params=_CALIBRATION_PARAMS,
    )
    cli_session = build_probe_pair_session(
        tmp_path / "parity-cli",
        duration_s=0.05,
        calibration_params=_CALIBRATION_PARAMS,
    )
    LntBackend().analyze_and_write(backend_session)
    backend_payload = json.loads(
        (backend_session / "metrics.json").read_text(encoding="utf-8"),
    )

    # When: the generic CLI analyze command runs on the twin session.
    code = main(["analyze", str(cli_session)])

    # Then: it exits cleanly and the cm_dm section is semantically equal to
    # the backend path: same status, same peak count, same conducted band.
    assert code == EXIT_OK
    cli_payload = json.loads((cli_session / "metrics.json").read_text(encoding="utf-8"))
    backend_section = backend_payload["cm_dm"]
    cli_section = cli_payload["cm_dm"]
    assert cli_section["status"] == backend_section["status"]
    assert len(cli_section["peaks"]) == len(backend_section["peaks"])
    assert cli_section["band_low_hz"] == pytest.approx(backend_section["band_low_hz"])
    assert cli_section["band_high_hz"] == pytest.approx(backend_section["band_high_hz"])
