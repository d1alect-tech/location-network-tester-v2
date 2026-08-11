"""Строгий контракт схемы эксперимента."""

from copy import deepcopy

import pytest

from lnt.context.json_codec import decode_object
from lnt.experiments import (
    Experiment,
    ExperimentValidationError,
    Protocol,
    experiment_from_mapping,
    experiment_to_canonical_json,
)
from tests.experiments.factories import make_experiment


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_all_protocols_have_byte_identical_canonical_round_trip(protocol: Protocol) -> None:
    # Given
    experiment = make_experiment(protocol)

    # When
    encoded = experiment_to_canonical_json(experiment)
    restored = experiment_from_mapping(decode_object(encoded.decode(), "experiment.json"))

    # Then
    assert experiment_to_canonical_json(restored) == encoded


@pytest.mark.parametrize(
    ("field", "reason_code"),
    [
        ("sampling_unit", "sampling_unit_missing"),
        ("pairing_key", "pairing_key_missing"),
        ("site_key", "hierarchy_key_missing"),
        ("subject_key", "hierarchy_key_missing"),
        ("block_key", "hierarchy_key_missing"),
        ("within_unit_aggregation", "aggregation_missing"),
        ("minimum_n", "minimum_n_missing"),
        ("independence_assumptions", "independence_missing"),
    ],
)
def test_missing_protocol_declaration_is_typed_rejection(field: str, reason_code: str) -> None:
    # Given
    raw = deepcopy(make_experiment().to_mapping())
    protocol = raw["protocol"]
    assert isinstance(protocol, dict)
    del protocol[field]

    # When / Then
    with pytest.raises(ExperimentValidationError) as raised:
        experiment_from_mapping(raw)
    assert raised.value.reason_code == reason_code
    assert str(raised.value).startswith("эксперимент:")


def test_duplicate_member_role_and_order_is_typed_error() -> None:
    # Given
    raw = deepcopy(make_experiment().to_mapping())
    members = raw["members"]
    assert isinstance(members, list)
    second = members[1]
    assert isinstance(second, dict)
    second["order"] = 1

    # When / Then
    with pytest.raises(ExperimentValidationError) as raised:
        experiment_from_mapping(raw)
    assert raised.value.reason_code == "duplicate_member_role_order"


def test_condition_assignment_has_no_label_inference_api() -> None:
    # Given / When
    fields = Experiment.model_fields

    # Then
    assert "label" not in fields
    assert "condition_inference" not in fields
