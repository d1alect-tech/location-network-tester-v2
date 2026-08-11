from __future__ import annotations

import pytest

from tests.science.truth import TruthMismatchError, verify_scalar


def test_verifier_accepts_value_inside_documented_tolerance() -> None:
    verify_scalar(10.04, expected=10.0, absolute_tolerance=0.05, rationale="FFT-bin width")


@pytest.mark.parametrize("mutation", [-1.0, 2.0, 10.1])
def test_verifier_rejects_sign_scale_and_bin_mutations(mutation: float) -> None:
    with pytest.raises(TruthMismatchError):
        verify_scalar(
            mutation,
            expected=1.0,
            absolute_tolerance=0.05,
            rationale="controlled mutation must exceed one FFT-bin tolerance",
        )
