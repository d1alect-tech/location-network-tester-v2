"""Диспетчер CM/DM-анализа: payload metrics.json, CSV-артефакт, калибровка."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.cm_dm.analysis import (
    CM_DM_SPECTRUM_FILENAME,
    analyze_cm_dm_session,
    cm_dm_analysis_to_payload,
    write_cm_dm_analysis,
)
from lnt.errors import InputError
from tests.cm_dm_fixtures import build_probe_pair_session

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_CSV_HEADER = "frequency_hz,cm_psd_v2_per_hz,dm_psd_v2_per_hz,coherence"


def _rewrite_manifest(session_dir: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    path = session_dir / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_analyze_rejects_single_channel(tmp_path: Path) -> None:
    # Given: a probe-pair session whose manifest declares CH2 absent.
    session_dir = build_probe_pair_session(tmp_path / "single", duration_s=0.05)
    _rewrite_manifest(session_dir, lambda payload: payload.update({"ch2": None}))

    # When / Then: analysis rejects the single-channel record.
    with pytest.raises(InputError, match="одноканаль"):
        analyze_cm_dm_session(session_dir)


def test_analyze_rejects_calibration_session_type(tmp_path: Path) -> None:
    # Given: a session whose manifest declares the calibration type.
    session_dir = build_probe_pair_session(tmp_path / "calibration", duration_s=0.05)
    _rewrite_manifest(
        session_dir,
        lambda payload: payload.update({"session_type": "cm_dm_calibration"}),
    )

    # When / Then: analysis refuses to treat a calibration record as measurement.
    with pytest.raises(InputError, match="калибровочн"):
        analyze_cm_dm_session(session_dir)


def test_analyze_sample_rate_below_band_raises(tmp_path: Path) -> None:
    # Given: fs=16 kHz, so 0.45*fs stays below the 9 kHz conducted band.
    session_dir = build_probe_pair_session(
        tmp_path / "lowfs",
        sample_rate_hz=16_000.0,
        duration_s=0.05,
    )

    # When / Then: analysis rejects the sample rate before any Welch work.
    with pytest.raises(InputError, match="полоса проводимых помех"):
        analyze_cm_dm_session(session_dir)


def test_payload_canonical_shape_with_cm_dm_section(tmp_path: Path) -> None:
    # Given: an analyzed probe-pair session without calibration parameters.
    session_dir = build_probe_pair_session(tmp_path / "shape", duration_s=0.05)
    result = analyze_cm_dm_session(session_dir)

    # When: the pure payload builder runs and artifacts are written.
    payload = cm_dm_analysis_to_payload(result)
    write_cm_dm_analysis(session_dir, result)

    # Then: the top-level key set is canonical plus "cm_dm"; legacy sections null.
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
    assert payload["schema_version"] == 2
    assert payload["session_type"] == "cm_dm"
    assert payload["needle"] is None
    assert payload["line_quality"] is None
    assert payload["spectrum"] is None
    assert payload["ch1_input_reference"] is None
    # And: the serialized cm_dm section carries the exact contract shape.
    written = json.loads((session_dir / "metrics.json").read_text(encoding="utf-8"))
    section = written["cm_dm"]
    assert set(section) == {
        "schema_version",
        "status",
        "calibration",
        "band_low_hz",
        "band_high_hz",
        "nperseg",
        "segment_count",
        "peaks",
    }
    assert section["schema_version"] == 1
    assert section["status"] == "unavailable"
    assert section["calibration"] is None
    assert section["band_low_hz"] == pytest.approx(9_000.0)
    assert section["band_high_hz"] == pytest.approx(900_000.0)
    assert isinstance(section["nperseg"], int)
    assert section["segment_count"] >= 1
    peaks = section["peaks"]
    assert 1 <= len(peaks) <= 8
    for peak in peaks:
        assert set(peak) == {"frequency_hz", "mode", "psd_v2_per_hz"}
        assert peak["mode"] in ("cm", "dm")
        assert peak["psd_v2_per_hz"] > 0.0


def test_calibration_status_ok_when_parameters_present(tmp_path: Path) -> None:
    # Given: a probe-pair session captured with published calibration scalars.
    session_dir = build_probe_pair_session(
        tmp_path / "calibrated",
        duration_s=0.05,
        calibration_params={
            "probe_pair_correction_factor": 1.04,
            "probe_pair_gain_ratio": 0.96,
            "probe_pair_rejection_depth_db": 31.5,
        },
    )

    # When: the session is analyzed.
    result = analyze_cm_dm_session(session_dir)

    # Then: status is ok and the three calibration floats round-trip.
    assert result.status == "ok"
    assert result.calibration is not None
    assert result.calibration.correction_factor == pytest.approx(1.04)
    assert result.calibration.gain_ratio_epsilon == pytest.approx(0.96)
    assert result.calibration.rejection_depth_db == pytest.approx(31.5)


def test_dm_tone_attributed_to_dm_mode(tmp_path: Path) -> None:
    # Given: a probe-pair session with a dominant DM tone and a weaker CM tone.
    session_dir = build_probe_pair_session(tmp_path / "dm-tone", cm_tone_hz=250_000.0)

    # When: the session is analyzed.
    result = analyze_cm_dm_session(session_dir)

    # Then: the dominant peak is the DM tone attributed to the dm mode.
    dominant = result.peaks[0]
    assert dominant.mode == "dm"
    assert dominant.frequency_hz == pytest.approx(100_000.0, rel=0.01)
    # And: the CM tone appears separately, attributed to the cm mode.
    modes_by_frequency = {peak.mode: peak for peak in result.peaks}
    assert modes_by_frequency["cm"].frequency_hz == pytest.approx(250_000.0, rel=0.01)


def test_csv_artifact_header_and_rows(tmp_path: Path) -> None:
    # Given: an analyzed probe-pair session with written artifacts.
    session_dir = build_probe_pair_session(tmp_path / "csv")
    result = analyze_cm_dm_session(session_dir)
    write_cm_dm_analysis(session_dir, result)

    # When: the CSV artifact is parsed.
    csv_path = session_dir / CM_DM_SPECTRUM_FILENAME
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    table = np.loadtxt(csv_path, delimiter=",", skiprows=1)

    # Then: the header matches the contract exactly and rows stay in-band.
    assert lines[0] == _CSV_HEADER
    assert table.ndim == 2
    assert table.shape[1] == 4
    frequencies = table[:, 0]
    assert frequencies.size >= 1
    assert float(frequencies.min()) >= 9_000.0
    assert float(frequencies.max()) <= 900_000.0
    coherence = table[:, 3]
    assert bool(np.all(coherence >= 0.0))
    assert bool(np.all(coherence <= 1.0 + 1e-9))


def test_metrics_json_written(tmp_path: Path) -> None:
    # Given: an analyzed probe-pair session.
    session_dir = build_probe_pair_session(tmp_path / "metrics", duration_s=0.05)
    result = analyze_cm_dm_session(session_dir)

    # When: artifacts are written.
    metrics_path = write_cm_dm_analysis(session_dir, result)

    # Then: metrics.json exists at the documented location with Welch metadata.
    assert metrics_path == session_dir / "metrics.json"
    assert metrics_path.is_file()
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["cm_dm"]["nperseg"] == 8192
    assert payload["cm_dm"]["segment_count"] >= 1
    assert (session_dir / CM_DM_SPECTRUM_FILENAME).is_file()
