"""Аналитические тесты движка F11 fixed_phase_band_f15_mode_empirical_distributions."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from lnt.characterization import f11_result
from lnt.characterization.f11_contract import F11Declarations
from lnt.characterization.f11_engine import compute_f11_conditional_distributions
from lnt.characterization.f11_result import (
    CDF_PROBABILITIES,
    MINIMUM_SUPPORT,
    QUANTILES,
    F11Event,
    F11EventInventory,
    F11Result,
    F15ModeSource,
)
from lnt.characterization.phase_model import PhaseCycles
from lnt.characterization.records import Status, Unit, validate_unit_name
from lnt.events.models import Polarity

FS_HZ = 1000.0
WINDOW_S = 0.02
PHASE_BINS = 16
BANDS = ((3000.0, 10000.0), (10000.0, 50000.0), (50000.0, 200000.0))
MODE_LABELS = ("mode_0", "mode_1", "mode_2", "mode_3")


def _phase(count: int = 1600, *, status: Status = Status.AVAILABLE) -> PhaseCycles:
    return PhaseCycles(
        sample_rate_hz=FS_HZ,
        sample_count=count,
        cycle_start_samples=np.asarray([0.0]),
        cycle_end_samples=np.asarray([float(count)]),
        cycle_valid=np.asarray([status is Status.AVAILABLE], dtype=np.bool_),
        status=status,
        reason_code=None if status is Status.AVAILABLE else "phase_reference_unavailable",
    )


def _modes() -> F15ModeSource:
    medoids = tuple(tuple(float(index == axis) for index in range(7)) for axis in range(4))
    return F15ModeSource(
        status=Status.AVAILABLE,
        window_s=WINDOW_S,
        overlap_fraction=0.0,
        feature_medians=(0.0,) * 7,
        feature_mads=(1.0,) * 7,
        canonical_labels=MODE_LABELS,
        canonical_standardized_features=medoids,
        window_features=(medoids[0],),
        window_labels=("mode_0",),
    )


def _events(count: int = 20) -> tuple[F11Event, ...]:
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
        for index in range(count)
    )


def _run(
    events: tuple[F11Event, ...],
    *,
    modes: F15ModeSource | None = None,
    phase: PhaseCycles | None = None,
    gaps: int = 0,
    band_rule: str = "left_closed_right_open_last_closed",
    minimum_support: int = MINIMUM_SUPPORT,
    maximum_events: int = 4096,
) -> F11Result:
    declarations = F11Declarations(
        phase_bins=PHASE_BINS,
        bands_hz=BANDS,
        band_interval_rule=band_rule,
        mode_source_family_id="f15_interpretable_modes",
        mode_conditioning_rule="event_peak_window_nearest_canonical_medoid",
        mode_count=4,
        mode_distance_tie_break="lowest_canonical_mode_label",
        quantities=(
            "absolute_peak_v",
            "duration_s",
            "dominant_frequency_hz",
            "v2_s",
            "polarity_counts",
        ),
        quantiles=QUANTILES,
        quantile_method="linear",
        cdf_points=CDF_PROBABILITIES.size,
        minimum_support=minimum_support,
        maximum_events=maximum_events,
    )
    return compute_f11_conditional_distributions(
        phase or _phase(),
        F11EventInventory(events=events, gap_count=gaps),
        modes or _modes(),
        declarations,
    )


def test_twenty_linear_events_recover_exact_distribution_truth() -> None:
    """Given 20 known events, when F11 bins them, then linear quantiles and CDF are exact."""
    result = _run(_events())

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert len(result.cells) == PHASE_BINS * len(BANDS) * 4
    cell = next(
        item
        for item in result.cells
        if (item.phase_bin, item.band_index, item.mode_label) == (0, 0, "mode_0")
    )
    assert cell.status is Status.AVAILABLE
    assert (cell.support_count, cell.positive_count, cell.negative_count) == (20, 10, 10)
    peak = cell.distributions[0]
    assert peak.quantiles == pytest.approx((2.9, 5.75, 10.5, 15.25, 18.1, 19.81))
    assert peak.cdf_probabilities is not None
    assert peak.cdf_probabilities[0] == pytest.approx(0.05)
    assert peak.cdf_probabilities[64] == pytest.approx(0.5)
    assert peak.cdf_probabilities[-1] == 1.0


def test_nonfinite_quantity_is_excluded_only_from_its_distribution() -> None:
    """Given one NaN peak, when F11 bins 20 events, then other quantities remain exact."""
    base = _events()
    result = _run((replace(base[0], absolute_peak_v=float("nan")), *base[1:]))

    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("insufficient_support",)
    assert result.n_missing == 1
    cell = next(item for item in result.cells if item.support_count == 20)
    assert cell.status is Status.PARTIAL
    assert cell.distributions[0].status is Status.UNAVAILABLE
    assert cell.distributions[0].missing_count == 1
    assert cell.distributions[0].quantiles == (None,) * len(QUANTILES)
    assert cell.distributions[1].status is Status.AVAILABLE


def test_persisted_quantity_names_match_the_unit_vocabulary() -> None:
    """Given locked quantity names, when unit suffixes validate, then all four pass."""
    units = (Unit.V, Unit.S, Unit.HZ, Unit.V2_S)
    assert units == f11_result.QUANTITY_UNITS
    for name, unit in zip(f11_result.PERSISTED_QUANTITY_NAMES, units, strict=True):
        validate_unit_name(name, unit)


def test_method_locked_recipe_and_reason_vocabulary_match_sources() -> None:
    """Given authoritative contract sources, when F11 publishes metadata, then values match."""
    assert f11_result.METHOD == "fixed_phase_band_f15_mode_empirical_distributions"
    assert f11_result.BANDS_HZ == BANDS
    assert f11_result.QUANTILES == (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)
    assert f11_result.CDF_PROBABILITIES.size == 129
    assert f11_result.MINIMUM_SUPPORT == 20
    assert f11_result.MAXIMUM_EVENTS == 4096
    assert f11_result.DECLARED_CODES == (
        "phase_reference_unavailable",
        "insufficient_support",
        "bin_empty",
        "dominant_band_unavailable",
        "mode_unavailable",
        "mode_assignment_unavailable",
        "event_limit",
        "gaps_present",
    )


def test_phase_and_frequency_edges_use_declared_interval_rules() -> None:
    """Given exact edges, when F11 bins peaks, then phase and bands are left-closed."""
    base = _events(4)
    events = (
        replace(base[0], peak_sample=99, dominant_frequency_hz=3000.0),
        replace(base[1], peak_sample=100, dominant_frequency_hz=9999.0),
        replace(base[2], peak_sample=100, dominant_frequency_hz=10000.0),
        replace(base[3], peak_sample=100, dominant_frequency_hz=200000.0),
    )

    feature = _modes().window_features[0]
    assert feature is not None
    modes = replace(
        _modes(),
        window_features=(None, None, None, None, feature, feature),
        window_labels=(None, None, None, None, "mode_0", "mode_0"),
    )
    result = _run(events, modes=modes, minimum_support=1)  # правила полос, не порог
    observed = {
        (item.phase_bin, item.band_index) for item in result.cells if item.support_count > 0
    }

    assert observed == {(0, 0), (1, 0), (1, 1), (1, 2)}


def test_unretained_window_uses_lowest_label_on_medoid_distance_tie() -> None:
    """Given equal standardized distances, when F11 assigns mode, then lowest label wins."""
    source = _modes()
    negative = tuple(-float(index == 0) for index in range(7))
    positive = tuple(float(index == 0) for index in range(7))
    medoids = (negative, positive, source.canonical_standardized_features[2], positive)
    modes = replace(
        source,
        canonical_labels=("mode_3", "mode_0", "mode_1", "mode_2"),
        canonical_standardized_features=medoids,
        window_features=((0.0,) * 7,),
        window_labels=(None,),
    )

    result = _run(_events(1), modes=modes, minimum_support=1)  # правило ничьей, не порог
    observed = {item.mode_label for item in result.cells if item.support_count == 1}

    assert observed == {"mode_0"}


def test_retained_f15_window_label_wins_without_recomputed_features() -> None:
    """Given retained label and absent features, when F11 assigns mode, then label is used."""
    modes = replace(_modes(), window_features=(None,), window_labels=("mode_1",))

    result = _run(_events(1), modes=modes, minimum_support=1)  # приоритет метки, не порог

    assert {item.mode_label for item in result.cells if item.support_count} == {"mode_1"}
    assert result.n_mode_missing == 0


def test_nineteen_events_report_insufficient_support_without_extrapolation() -> None:
    """Given 19 events, when support is below the minimum, then nothing is published."""
    result = _run(_events(19))

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("insufficient_support",)
    # Дом: UNAVAILABLE публикует пустые домены, поэтому ни 19-элементной ячейки,
    # ни квантилей, ни CDF не экстраполируется — правду несёт сам код.
    assert result.cells == ()
    assert all(len(grid) == 0 for grid in result.cdf_grids)


def test_empty_cells_stay_explicit_without_degrading_supported_family() -> None:
    """Given one supported cell, when 191 cells are empty, then each reports bin_empty."""
    result = _run(_events())
    empty = [item for item in result.cells if item.support_count == 0]

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert len(empty) == 16 * 3 * 4 - 1
    assert {item.reason_codes for item in empty} == {("bin_empty",)}
    assert all(item.status is Status.UNAVAILABLE for item in empty)


def test_unavailable_f15_result_makes_f11_unavailable_without_fabrication() -> None:
    """Given unavailable F15, when F11 runs, then mode_unavailable is returned with no cells."""
    result = _run(_events(), modes=replace(_modes(), status=Status.UNAVAILABLE))

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("mode_unavailable",)
    assert result.cells == ()
    assert result.evaluated_event_count == 0
    assert all(len(grid) == 0 for grid in result.cdf_grids)


def test_unavailable_phase_root_maps_to_declared_family_reason() -> None:
    """Given unavailable phase, when F11 runs, then no phase-conditioned cell is published."""
    result = _run(_events(), phase=_phase(0, status=Status.UNAVAILABLE))

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("phase_reference_unavailable",)
    assert result.cells == ()
    assert result.n_phase_unavailable == 20


def test_missing_f15_feature_vector_excludes_event_and_counts_mode_missing() -> None:
    """Given peaks beyond retained F15 windows, when F11 runs, then mode support stays empty."""
    events = tuple(
        replace(event, peak_sample=event.peak_sample + 20, peak_time_s=event.peak_time_s + 0.02)
        for event in _events()
    )

    result = _run(events)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("mode_assignment_unavailable",)
    assert result.n_mode_missing == 20
    assert result.n_missing == 0
    assert result.cells == ()


# Конец аналитических срезов F11.
