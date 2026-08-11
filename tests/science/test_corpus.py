from __future__ import annotations

import numpy as np
import pytest

from tests.science.corpus import RATE_HZ, all_fixtures
from tests.science.truth import verify_scalar


def test_inventory_is_complete_and_every_truth_explains_tolerance() -> None:
    fixtures = all_fixtures()
    assert {fixture.name for fixture in fixtures} == {
        "pure_tone",
        "multitone_harmonics",
        "chirp",
        "am",
        "switching_burst",
        "impulses",
        "clipping",
        "dropout",
        "drift",
        "baseline_excess",
        "aba_effect",
    }
    assert all(fixture.truth.tolerance_rationale for fixture in fixtures)
    assert all(fixture.sample_rate_hz == RATE_HZ for fixture in fixtures)


@pytest.mark.parametrize("index", range(11))
def test_double_generation_has_identical_hash(index: int) -> None:
    assert all_fixtures()[index].digest() == all_fixtures()[index].digest()


@pytest.mark.parametrize("index", range(11))
def test_time_domain_rms_matches_analytic_truth(index: int) -> None:
    fixture = all_fixtures()[index]
    measured = float(np.sqrt(np.mean(fixture.samples.astype(np.float64) ** 2)))
    tolerance = max(
        1e-6, fixture.truth.rms_v * (0.05 if fixture.name == "baseline_excess" else 0.015)
    )
    verify_scalar(
        measured,
        expected=fixture.truth.rms_v,
        absolute_tolerance=tolerance,
        rationale=fixture.truth.tolerance_rationale,
    )


def test_aba_effect_truth_is_explicit_and_independently_recovered() -> None:
    fixture = all_fixtures()[-1]
    blocks = np.split(fixture.samples, 4)
    measured = (float(np.mean(blocks[1])) + float(np.mean(blocks[3]))) / 2 - (
        float(np.mean(blocks[0])) + float(np.mean(blocks[2]))
    ) / 2
    assert fixture.truth.block_labels == ("A1", "B1", "A2", "B2")
    verify_scalar(
        measured,
        expected=fixture.truth.effect_size_v or 0.0,
        absolute_tolerance=0.001,
        rationale=fixture.truth.tolerance_rationale,
    )
