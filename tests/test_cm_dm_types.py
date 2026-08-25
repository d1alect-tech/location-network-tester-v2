"""T3 (CM/DM-план): новые члены SessionType и неизменность кодека манифеста."""

from __future__ import annotations

import json

from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.types import (
    SCHEMA_VERSION,
    ChannelMeta,
    ChannelRole,
    ParameterValue,
    SessionManifest,
    SessionSource,
    SessionType,
)


def _cm_dm_manifest(parameters: dict[str, ParameterValue]) -> SessionManifest:
    return SessionManifest(
        schema_version=SCHEMA_VERSION,
        session_id="ses-cmdm-0001",
        created_utc="2026-08-25T09:00:00+00:00",
        completed_utc="2026-08-25T09:00:02+00:00",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.CM_DM,
        sample_rate_hz=8_000_000.0,
        duration_s=2.4,
        sample_count=19_200_000,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters=parameters,
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="x2",
            range_code=2,
            probe_multiplier=1.0,
        ),
        ch2=None,
        acquisition_telemetry=None,
        synthetic_truth=None,
    )


def test_cm_dm_session_type_values() -> None:
    assert SessionType.CM_DM.value == "cm_dm"
    assert SessionType.CM_DM_CALIBRATION.value == "cm_dm_calibration"


def test_manifest_roundtrip_with_probe_pair_parameters() -> None:
    parameters: dict[str, ParameterValue] = {
        "probe_pair": "l_n",
        "probe_pair_correction_factor": 1.08,
        "probe_pair_gain_ratio": 0.92,
        "probe_pair_rejection_depth_db": 34.5,
        "probe_pair_calibration": "cal-000001",
    }
    manifest = _cm_dm_manifest(parameters)

    mapping = manifest_to_mapping(manifest)
    restored = manifest_from_mapping(mapping)

    assert restored == manifest


def test_session_type_parses_from_mapping() -> None:
    base = manifest_to_mapping(_cm_dm_manifest({}))

    for raw in ("cm_dm", "cm_dm_calibration"):
        mapping = dict(base)
        mapping["session_type"] = raw
        parsed = manifest_from_mapping(json.loads(json.dumps(mapping)))
        assert parsed.session_type.value == raw
