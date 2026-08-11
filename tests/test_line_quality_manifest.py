"""Контракт домена/манифеста режима качества сети (transformer_line_probe_v1)."""

from __future__ import annotations

import pytest

from lnt._manifest_ch1_setup import (
    parse_ch1_setup,
    serialize_ch1_setup,
    validate_session_setup_pairing,
)
from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.errors import InputError
from lnt.types import (
    FloatingDifferentialRcShunt,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)

TRANSFORMER_KIND = "transformer_line_probe_v1"


def _transformer_setup_mapping() -> dict[str, object]:
    return {
        "kind": TRANSFORMER_KIND,
        "nominal_primary_v": 230.0,
        "nominal_secondary_v": 6.0,
        "probe_multiplier": 10.0,
    }


def _line_quality_manifest_mapping() -> dict[str, object]:
    return {
        "schema_version": 2,
        "session_id": "line-quality-contract",
        "created_utc": "2026-08-05T00:00:00Z",
        "completed_utc": "2026-08-05T00:00:02Z",
        "source": "device",
        "session_type": "line_quality",
        "sample_rate_hz": 8_000_000.0,
        "duration_s": 2.4,
        "sample_count": 19_200_000,
        "line_frequency_hz": 50.0,
        "profile": None,
        "baseline_session": None,
        "parameters": {},
        "ch1": {
            "filename": "ch1.npy",
            "role": "lf_transformer",
            "unit": "V",
            "front_end": "transformer 230:6",
            "range_code": 1,
            "probe_multiplier": 10.0,
        },
        "ch2": None,
        "acquisition_telemetry": None,
        "synthetic_truth": None,
        "ch1_setup": _transformer_setup_mapping(),
    }


def test_session_type_enum_has_line_quality() -> None:
    # Then: the line-quality session type is a first-class protocol member.
    assert SessionType.LINE_QUALITY.value == "line_quality"


def test_transformer_line_probe_rejects_non_positive_values() -> None:
    # When/Then: non-physical nominals are rejected at the domain boundary.
    with pytest.raises(InputError):
        TransformerLineProbe(
            nominal_primary_v=0.0,
            nominal_secondary_v=6.0,
            probe_multiplier=10.0,
        )
    with pytest.raises(InputError):
        TransformerLineProbe(
            nominal_primary_v=230.0,
            nominal_secondary_v=6.0,
            probe_multiplier=float("nan"),
        )


def test_transformer_setup_serialization_round_trip() -> None:
    # Given: an explicit transformer front-end model.
    setup = TransformerLineProbe(
        nominal_primary_v=230.0,
        nominal_secondary_v=6.0,
        probe_multiplier=10.0,
    )

    # When: the setup crosses the typed JSON boundary twice.
    serialized = serialize_ch1_setup(setup)
    restored = parse_ch1_setup(serialized)

    # Then: the discriminated kind and every nominal survive.
    assert serialized == _transformer_setup_mapping()
    assert restored == setup


def test_transformer_setup_parse_rejects_unknown_fields() -> None:
    # Given: a transformer mapping with a stray field.
    mapping = _transformer_setup_mapping()
    mapping["extra"] = 1.0

    # When/Then: strict parsing refuses silent extensions.
    with pytest.raises(InputError):
        parse_ch1_setup(mapping)


def test_pairing_accepts_line_quality_with_transformer_setup() -> None:
    # Given: the only valid line-quality pairing.
    setup = TransformerLineProbe(
        nominal_primary_v=230.0,
        nominal_secondary_v=6.0,
        probe_multiplier=10.0,
    )

    # When/Then: no error is raised.
    validate_session_setup_pairing(SessionType.LINE_QUALITY, setup)


@pytest.mark.parametrize(
    ("session_type", "setup"),
    [
        (
            SessionType.LINE_QUALITY,
            ScopeInputTerminated(termination_resistance_ohm=50.0),
        ),
        (
            SessionType.MEASUREMENT,
            TransformerLineProbe(
                nominal_primary_v=230.0,
                nominal_secondary_v=6.0,
                probe_multiplier=10.0,
            ),
        ),
        (
            SessionType.SELF_NOISE,
            TransformerLineProbe(
                nominal_primary_v=230.0,
                nominal_secondary_v=6.0,
                probe_multiplier=10.0,
            ),
        ),
    ],
)
def test_pairing_rejects_transformer_setup_mismatches(
    session_type: SessionType,
    setup: FloatingDifferentialRcShunt | ScopeInputTerminated | TransformerLineProbe,
) -> None:
    # When/Then: any non-canonical pairing fails validation.
    with pytest.raises(InputError):
        validate_session_setup_pairing(session_type, setup)


def test_line_quality_manifest_round_trip() -> None:
    # Given: a complete schema-v2 line-quality manifest mapping.
    mapping = _line_quality_manifest_mapping()

    # When: it crosses the typed JSON boundary twice.
    restored = manifest_from_mapping(mapping)
    serialized = manifest_to_mapping(restored)

    # Then: session type, transformer setup, and CH1 meta survive intact.
    assert restored.session_type is SessionType.LINE_QUALITY
    assert isinstance(restored.ch1_setup, TransformerLineProbe)
    assert restored.ch1.probe_multiplier == 10.0
    assert serialized == mapping
