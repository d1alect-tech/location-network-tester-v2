from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from lnt.characterization import (
    FAMILY_IDS,
    CharacterizationBundle,
    CharacterizationError,
    FamilyResult,
    ScalarSummary,
    Status,
    Support,
    Unit,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_bundle_requires_exact_18_family_ids_in_order(bundle: CharacterizationBundle) -> None:
    assert tuple(result.family_id for result in bundle.families) == FAMILY_IDS
    with pytest.raises(CharacterizationError, match="family_order"):
        CharacterizationBundle(families=tuple(reversed(bundle.families)))


def test_records_are_immutable(bundle: CharacterizationBundle) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        FamilyResult.__setattr__(bundle.families[0], "status", Status.PARTIAL)


def _replace_first(
    bundle: CharacterizationBundle,
    mutate: Callable[[FamilyResult], FamilyResult],
) -> tuple[FamilyResult, ...]:
    return (mutate(bundle.families[0]), *bundle.families[1:])


def _available_with_reason(result: FamilyResult) -> FamilyResult:
    return dataclasses.replace(result, reason_codes=("unexpected",))


def _partial_without_output(result: FamilyResult) -> FamilyResult:
    return dataclasses.replace(
        result, status=Status.PARTIAL, reason_codes=("clipped",), comparison_summary=()
    )


def _unavailable_with_output(result: FamilyResult) -> FamilyResult:
    return dataclasses.replace(result, status=Status.UNAVAILABLE, reason_codes=("missing",))


@pytest.mark.parametrize(
    "mutate",
    [
        _available_with_reason,
        _partial_without_output,
        _unavailable_with_output,
    ],
)
def test_status_invariants_fail_closed(
    bundle: CharacterizationBundle,
    mutate: Callable[[FamilyResult], FamilyResult],
) -> None:
    with pytest.raises(CharacterizationError, match="status_invariant"):
        CharacterizationBundle(families=_replace_first(bundle, mutate))


def test_summary_unit_suffix_is_checked() -> None:
    with pytest.raises(CharacterizationError, match="unit_suffix"):
        ScalarSummary(name="frequency_s", value=50.0, unit=Unit.HZ)


def test_support_arithmetic_and_bounds_are_checked() -> None:
    with pytest.raises(CharacterizationError, match="support_counts"):
        Support(
            start_s=0.0,
            end_s=1.0,
            duration_s=1.0,
            sample_count=10,
            observation_count=9,
            missing_count=2,
            stored_count=9,
            selection_rule="all",
        )
