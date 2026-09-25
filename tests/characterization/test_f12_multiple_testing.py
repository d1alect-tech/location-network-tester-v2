"""Аналитические тесты BH и connected significant band F12."""

from __future__ import annotations

import numpy as np
import pytest

from lnt.characterization.f12_candidates import CandidateTable
from lnt.characterization.f12_inference import infer_f12_candidates
from lnt.characterization.f12_multiple_testing import (
    benjamini_hochberg,
    bounded_significant_order,
    connected_significant_band,
)


def test_bh_matches_hand_computed_family_wide_step_up() -> None:
    """m=4: sorted .002,.01,.03,.04 даёт adjusted .008,.02,.04,.04."""
    raw = np.asarray([0.01, 0.04, 0.03, 0.002], dtype=np.float64)

    adjusted = benjamini_hochberg(raw)

    assert adjusted.tolist() == pytest.approx([0.02, 0.04, 0.04, 0.008], rel=1e-15)


def test_selected_band_is_contiguous_significant_run_around_maximum() -> None:
    """Maximum at bin 2 selects bins 2..4 и не пересекает соседний nonsignificant bin."""
    frequencies = np.arange(3000.0, 3750.0, 125.0)
    adjusted = np.asarray([0.001, 0.2, 0.01, 0.03, 0.04, 0.2])

    selected = connected_significant_band(frequencies, adjusted, 0.05, 2)

    assert selected == (3250.0, 3500.0)


def test_stored_cap_preserves_selected_band_before_other_significant_bins() -> None:
    """При cap=3 весь selected run 3..5 сохраняется; остальные bins уступают место."""
    order = bounded_significant_order(
        np.asarray([0, 1, 2, 3, 4, 5, 6], dtype=np.int64),
        np.asarray([3, 4, 5], dtype=np.int64),
        3,
    )

    assert order.tolist() == [3, 4, 5]
    assert bounded_significant_order(
        np.asarray([0, 1, 2, 3, 4, 5, 6], dtype=np.int64),
        np.asarray([3, 4, 5], dtype=np.int64),
        1,
        maximum_index=5,
    ).tolist() == [5]


def test_inference_applies_cap_after_global_bh_and_keeps_maximum() -> None:
    """Ten equal floor-p candidates become ten significant cells; cap keeps max first."""
    candidates = CandidateTable(
        scale_index=np.zeros(10, dtype=np.int64),
        frequencies_hz=np.arange(3000.0, 3010.0, 1.0),
        spectral_kurtosis=np.arange(1.0, 11.0),
    )

    selection = infer_f12_candidates(
        candidates,
        np.zeros(199, dtype=np.float64),
        false_discovery_rate=0.05,
        maximum_stored_bins=3,
    )

    assert selection.significant_count == 10
    assert selection.stored_indices.tolist() == [9, 0, 1]
    assert selection.adjusted_p_value == pytest.approx([0.005, 0.005, 0.005])
    assert selection.maximum_index == 9
