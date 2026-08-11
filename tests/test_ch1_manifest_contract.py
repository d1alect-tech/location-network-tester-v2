from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.errors import InputError
from lnt.types import SessionType
from tests.ch1_contract_fixtures import floating_measurement_setup, self_noise_setup


def _schema_v1_mapping() -> dict[str, object]:
    return {
        "schema_version": 1,
        "session_id": "ch1-contract-v1",
        "created_utc": "2026-08-04T00:00:00Z",
        "completed_utc": "2026-08-04T00:00:02Z",
        "source": "device",
        "session_type": "measurement",
        "sample_rate_hz": 8_000_000.0,
        "duration_s": 2.4,
        "sample_count": 19_200_000,
        "line_frequency_hz": 50.0,
        "profile": None,
        "baseline_session": None,
        "parameters": {},
        "ch1": {
            "filename": "ch1.npy",
            "role": "hf_probe",
            "unit": "V",
            "front_end": "x2-probe 2x10nF+100R",
            "range_code": 1,
            "probe_multiplier": 1.0,
        },
        "ch2": {
            "filename": "ch2.npy",
            "role": "lf_transformer",
            "unit": "V",
            "front_end": "transformer 230:6",
            "range_code": 1,
            "probe_multiplier": 1.0,
        },
        "acquisition_telemetry": None,
        "synthetic_truth": None,
    }


def _schema_v2_mapping(*, session_type: str, setup: dict[str, object]) -> dict[str, object]:
    mapping = _schema_v1_mapping()
    mapping["schema_version"] = 2
    mapping["session_id"] = f"ch1-contract-{session_type}"
    mapping["session_type"] = session_type
    mapping["ch1_setup"] = setup
    return mapping


@pytest.mark.parametrize("basis", ["nominal", "operator_measured"])
def test_schema_v2_round_trips_discriminated_floating_rc_measurement_setup(
    basis: str,
) -> None:
    # Given: a device measurement whose CH1 model is explicit rather than inferred.
    mapping = _schema_v2_mapping(
        session_type="measurement",
        setup={
            "kind": "floating_differential_rc_shunt_v1",
            "resistance_ohm": 100.0,
            "c1_f": 10e-9,
            "c2_f": 10e-9,
            "component_values_basis": basis,
            "reference_assumption": "floating_host_unverified",
        },
    )

    # When: the manifest crosses the typed JSON boundary twice.
    restored = manifest_from_mapping(mapping)
    serialized = manifest_to_mapping(restored)

    # Then: the complete discriminated setup is stable and machine-readable.
    assert serialized == mapping


def test_schema_v2_round_trips_discriminated_scope_terminated_self_noise_setup() -> None:
    # Given: an explicit self-noise termination setup.
    mapping = _schema_v2_mapping(
        session_type="self_noise",
        setup={
            "kind": "scope_input_terminated_v1",
            "termination_resistance_ohm": 50.0,
        },
    )

    # When: it is parsed and serialized through the public manifest contract.
    serialized = manifest_to_mapping(manifest_from_mapping(mapping))

    # Then: the self-noise discriminator and its termination value survive exactly.
    assert serialized == mapping


def test_schema_v1_round_trips_without_ch1_setup_key() -> None:
    # Given: a persisted schema-v1 manifest with free-text front-end metadata.
    mapping = _schema_v1_mapping()

    # When: legacy data is loaded and written back.
    serialized = manifest_to_mapping(manifest_from_mapping(mapping))

    # Then: v1 remains byte-shape compatible and does not acquire v2 metadata.
    assert serialized == mapping
    assert "ch1_setup" not in serialized


def test_schema_v2_rejects_free_text_front_end_as_a_ch1_setup_substitute() -> None:
    # Given: a v2 measurement that has only the legacy CH1 front-end label.
    mapping = _schema_v2_mapping(
        session_type="measurement",
        setup={
            "kind": "floating_differential_rc_shunt_v1",
            "resistance_ohm": 100.0,
            "c1_f": 10e-9,
            "c2_f": 10e-9,
            "component_values_basis": "nominal",
            "reference_assumption": "floating_host_unverified",
        },
    )
    no_setup = deepcopy(mapping)
    del no_setup["ch1_setup"]

    # When: the v2 manifest is parsed without its discriminator.
    # Then: free text cannot silently become a measurement model.
    with pytest.raises(InputError):
        manifest_from_mapping(no_setup)


@pytest.mark.parametrize(
    ("session_type", "valid_session_type", "setup"),
    [
        ("measurement", "self_noise", self_noise_setup()),
        ("self_noise", "measurement", floating_measurement_setup()),
    ],
)
def test_schema_v2_rejects_contradictory_session_setup_pairings_on_parse_and_serialize(
    session_type: str,
    valid_session_type: str,
    setup: dict[str, object],
) -> None:
    # Given: a setup discriminator that belongs to the opposite session type.
    contradictory = _schema_v2_mapping(session_type=session_type, setup=setup)
    valid = _schema_v2_mapping(session_type=valid_session_type, setup=setup)

    # When: contradictory persisted data is parsed or a valid object is mutated in memory.
    with pytest.raises(InputError):
        manifest_from_mapping(contradictory)
    mutated = replace(manifest_from_mapping(valid), session_type=SessionType(session_type))

    # Then: both public schema boundaries reject the invalid pairing.
    with pytest.raises(InputError):
        manifest_to_mapping(mutated)
