"""Аналитические тесты F15-стратификации и общей сетки F11."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from lnt.characterization.f11_contract import F11Declarations
from lnt.characterization.f11_engine import compute_f11_conditional_distributions
from lnt.characterization.f11_result import (
    CDF_PROBABILITIES,
    QUANTILES,
    QUANTITIES,
    F11Event,
    F11EventInventory,
    F11Result,
    F15ModeSource,
)
from lnt.characterization.phase_model import PhaseCycles
from lnt.characterization.records import Status
from lnt.events.models import Polarity

FS_HZ = 1000.0
BANDS = ((3000.0, 10000.0), (10000.0, 50000.0), (50000.0, 200000.0))
LABELS = ("mode_0", "mode_1", "mode_2", "mode_3")


def _phase() -> PhaseCycles:
    return PhaseCycles(
        sample_rate_hz=FS_HZ,
        sample_count=1600,
        cycle_start_samples=np.asarray([0.0]),
        cycle_end_samples=np.asarray([1600.0]),
        cycle_valid=np.asarray([True], dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _modes() -> F15ModeSource:
    medoids = tuple(tuple(float(index == axis) for index in range(7)) for axis in range(4))
    return F15ModeSource(
        status=Status.AVAILABLE,
        window_s=0.02,
        overlap_fraction=0.0,
        feature_medians=(0.0,) * 7,
        feature_mads=(1.0,) * 7,
        canonical_labels=LABELS,
        canonical_standardized_features=medoids,
        window_features=medoids,
        window_labels=(None, None, None, None),
    )


def _events() -> tuple[F11Event, ...]:
    return tuple(
        F11Event(
            ordinal=index,
            peak_sample=index,
            peak_time_s=index / FS_HZ,
            polarity=Polarity.POSITIVE if index % 2 == 0 else Polarity.NEGATIVE,
            absolute_peak_v=float(index + 1),
            duration_s=float(index + 1) / 1000.0,
            dominant_frequency_hz=5000.0 + index,
            v2_s=0.5 * float(index + 1),
        )
        for index in range(20)
    )


def _run(events: tuple[F11Event, ...], modes: F15ModeSource) -> F11Result:
    declarations = F11Declarations(
        phase_bins=16,
        bands_hz=BANDS,
        band_interval_rule="left_closed_right_open_last_closed",
        mode_source_family_id="f15_interpretable_modes",
        mode_conditioning_rule="event_peak_window_nearest_canonical_medoid",
        mode_count=4,
        mode_distance_tie_break="lowest_canonical_mode_label",
        quantities=QUANTITIES,
        quantiles=QUANTILES,
        quantile_method="linear",
        cdf_points=CDF_PROBABILITIES.size,
        minimum_support=20,
        maximum_events=4096,
    )
    return compute_f11_conditional_distributions(
        _phase(), F11EventInventory(events=events), modes, declarations
    )


def test_identical_multisets_in_each_mode_give_identical_summaries() -> None:
    """Given same 20 values and polarities per mode, when F11 bins, then all summaries match."""
    source = _modes()
    template = _events()
    events = tuple(
        replace(
            template[index % 20],
            ordinal=mode * 20 + index % 20,
            peak_sample=mode * 20 + index % 20,
            peak_time_s=(mode * 20 + index % 20) / FS_HZ,
        )
        for mode in range(4)
        for index in range(20)
    )

    cells = [item for item in _run(events, source).cells if item.support_count == 20]
    assert [item.support_count for item in cells] == [20, 20, 20, 20]
    reference = cells[0]
    for cell in cells[1:]:
        assert (cell.positive_count, cell.negative_count) == (
            reference.positive_count,
            reference.negative_count,
        )
        assert tuple(item.quantiles for item in cell.distributions) == tuple(
            item.quantiles for item in reference.distributions
        )
        assert tuple(item.cdf_probabilities for item in cell.distributions) == tuple(
            item.cdf_probabilities for item in reference.distributions
        )


def test_mode_cdfs_share_one_family_wide_min_to_max_grid() -> None:
    """Given pooled peak range 1..120, when each mode CDF is built, then both use that grid."""
    source = _modes()
    first = _events()
    second = tuple(
        replace(
            event,
            ordinal=20 + index,
            peak_sample=20 + index,
            peak_time_s=(20 + index) / FS_HZ,
            absolute_peak_v=float(event.absolute_peak_v or 0.0) + 100.0,
        )
        for index, event in enumerate(first)
    )

    result = _run((*first, *second), source)
    cells = {item.mode_label: item for item in result.cells if item.support_count == 20}
    low = cells["mode_0"].distributions[0].cdf_probabilities
    high = cells["mode_1"].distributions[0].cdf_probabilities

    assert result.cdf_grids[0][0] == 1.0
    assert result.cdf_grids[0][-1] == 120.0
    assert low is not None
    assert high is not None
    assert (low[0], low[64], low[-1]) == (0.05, 1.0, 1.0)
    assert (high[0], high[118], high[-1]) == (0.0, 0.5, 1.0)
