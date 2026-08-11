from __future__ import annotations

import json

import pytest

from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.errors import InputError
from lnt.types import (
    SCHEMA_VERSION,
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
)


def _valid_mapping() -> dict[str, object]:
    return {
        "schema_version": 1,
        "session_id": "synthetic-001",
        "created_utc": "2026-08-04T00:00:00Z",
        "completed_utc": "2026-08-04T00:00:02Z",
        "source": "synthetic",
        "session_type": "measurement",
        "sample_rate_hz": 8_000_000.0,
        "duration_s": 2.4,
        "sample_count": 19_200_000,
        "line_frequency_hz": 50.0,
        "profile": "quiet",
        "baseline_session": None,
        "parameters": {"label": "qa", "seed": 7},
        "ch1": {
            "filename": "ch1.npy",
            "role": "hf_probe",
            "unit": "V",
            "front_end": "x2",
            "range_code": 2,
            "probe_multiplier": 1.0,
        },
        "ch2": {
            "filename": "ch2.npy",
            "role": "lf_transformer",
            "unit": "V",
            "front_end": "transformer",
            "range_code": 2,
            "probe_multiplier": 1.0,
        },
        "acquisition_telemetry": None,
        "synthetic_truth": None,
    }


def make_manifest(
    *,
    sample_count: int = 19_200_000,
) -> SessionManifest:
    return SessionManifest(
        schema_version=SCHEMA_VERSION,
        session_id="ses-test-0001",
        created_utc="2026-07-25T09:00:00+00:00",
        completed_utc="2026-07-25T09:00:02+00:00",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=8_000_000.0,
        duration_s=2.4,
        sample_count=sample_count,
        line_frequency_hz=50.0,
        profile="bad",
        baseline_session=None,
        parameters={"label": "qa", "seed": 7},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="x2",
            range_code=2,
            probe_multiplier=1.0,
        ),
        ch2=ChannelMeta(
            filename="ch2.npy",
            role=ChannelRole.LF_TRANSFORMER,
            unit="V",
            front_end="transformer",
            range_code=2,
            probe_multiplier=1.0,
        ),
        acquisition_telemetry=None,
        synthetic_truth=None,
    )


def test_manifest_round_trip_when_schema_v1_mapping_is_valid() -> None:
    manifest = manifest_from_mapping(_valid_mapping())

    restored = manifest_from_mapping(json.loads(json.dumps(manifest_to_mapping(manifest))))

    assert restored == manifest


def test_manifest_rejects_unknown_and_missing_top_level_fields() -> None:
    unknown = _valid_mapping()
    unknown["unexpected"] = 1
    missing = _valid_mapping()
    del missing["session_id"]

    with pytest.raises(InputError, match="неизвестные поля"):
        manifest_from_mapping(unknown)
    with pytest.raises(InputError, match="отсутствует поле 'session_id'"):
        manifest_from_mapping(missing)


def test_manifest_rejects_boolean_and_nonfinite_numeric_values() -> None:
    boolean = _valid_mapping()
    boolean["sample_count"] = True
    nonfinite = _valid_mapping()
    nonfinite["sample_rate_hz"] = float("nan")

    with pytest.raises(InputError, match="целым числом"):
        manifest_from_mapping(boolean)
    with pytest.raises(InputError, match="конечным"):
        manifest_from_mapping(nonfinite)
