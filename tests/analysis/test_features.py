from __future__ import annotations

import json

import numpy as np
import pytest

from lnt.events.models import CandidateEvent, EventInventory, Polarity, QualificationStatus
from lnt.events.settings import event_preset
from lnt.features import (
    BandDefinition,
    BandOverlapPolicy,
    BandSet,
    EstimandDirection,
    FeatureSchemaError,
    FrequencyUnit,
    PeakObservation,
    QualifiedPeak,
    compute_event_features,
    compute_psd_features,
    compute_spectrogram_features,
    feature_band_preset,
    track_peak_trajectories,
)
from lnt.psd.models import PsdResult
from lnt.spectrogram.models import SpectrogramOverview, StftSettings


def _psd_result(power: np.ndarray, *, frequencies: np.ndarray | None = None) -> PsdResult:
    frequency_hz = np.arange(power.size, dtype=np.float64) if frequencies is None else frequencies
    with np.errstate(divide="ignore", invalid="ignore"):
        level_db = 10.0 * np.log10(power)
    return PsdResult(
        frequency_hz=frequency_hz,
        psd_v2_per_hz=np.asarray(power, dtype=np.float64),
        asd_v_per_sqrt_hz=np.sqrt(power),
        level_db_v2_per_hz=level_db,
        band_rms=(),
        segment_count=8,
    )


def _band(*, low_hz: float = 1.0, high_hz: float = 5.0) -> BandDefinition:
    return BandDefinition(
        name="needle",
        low=low_hz,
        high=high_hz,
        unit=FrequencyUnit.HZ,
        direction=EstimandDirection.LOWER,
    )


def test_band_power_matches_analytic_rectangular_psd() -> None:
    # Given: five one-hertz bins carrying exactly 2 V²/Hz.
    result = _psd_result(np.full(7, 2.0, dtype=np.float64))
    bands = BandSet(bands=(_band(),), overlap_policy=BandOverlapPolicy.NON_OVERLAPPING)

    # When
    feature = compute_psd_features(result, bands).bands[0]

    # Then: BandRms-compatible inclusive-bin integration is 10 V².
    assert feature.integrated_power_v2 == pytest.approx(10.0)
    assert feature.rms_v == pytest.approx(np.sqrt(10.0))
    assert feature.noise_floor.median_v2_per_hz == pytest.approx(2.0)
    assert feature.noise_floor.p05_v2_per_hz == pytest.approx(2.0)
    assert feature.noise_floor.p95_v2_per_hz == pytest.approx(2.0)
    assert json.loads(json.dumps(feature.to_dict()))["direction"] == "lower"


def test_band_schema_validates_overlap_units_and_direction() -> None:
    # Given / When / Then: overlap is rejected only under the declared strict policy.
    overlapping = (
        _band(low_hz=1.0, high_hz=4.0),
        BandDefinition(
            name="second",
            low=3.0,
            high=5.0,
            unit=FrequencyUnit.HZ,
            direction=EstimandDirection.LOWER,
        ),
    )
    with pytest.raises(FeatureSchemaError, match="пересекаются"):
        BandSet(bands=overlapping, overlap_policy=BandOverlapPolicy.NON_OVERLAPPING)
    assert (
        len(BandSet(bands=overlapping, overlap_policy=BandOverlapPolicy.OVERLAPPING_ALLOWED).bands)
        == 2
    )
    with pytest.raises(FeatureSchemaError, match="единица"):
        BandDefinition.parse(name="bad", low=1.0, high=2.0, unit="rpm", direction="descriptive")
    with pytest.raises(FeatureSchemaError, match="direction"):
        BandDefinition.parse(name="bad", low=1.0, high=2.0, unit="Hz")


def test_builtin_band_grid_is_versioned_and_recipe_aligned() -> None:
    # Given / When
    preset = feature_band_preset("lnt_working_v1")

    # Then
    assert preset.feature_schema_version == 1
    assert tuple(band.name for band in preset.bands) == ("low", "mid", "high")
    assert tuple(band.low_hz for band in preset.bands) == (3_000.0, 30_000.0, 300_000.0)
    assert tuple(band.high_hz for band in preset.bands) == (30_000.0, 300_000.0, 3_000_000.0)


def test_q_is_refused_when_missing_bin_breaks_half_power_region() -> None:
    # Given: a clear peak whose right half-power route is interrupted by NaN.
    result = _psd_result(np.array([1.0, 2.0, 6.0, 10.0, np.nan, 2.0, 1.0]))
    bands = BandSet(bands=(_band(low_hz=0.0, high_hz=6.0),))

    # When
    peak = compute_psd_features(result, bands).bands[0].peak

    # Then
    assert peak is not None
    assert peak.prominence_db == pytest.approx(10.0 * np.log10(10.0 / 2.0))
    assert peak.q_factor is None
    assert peak.q_reason_code == "unqualified_gap"
    assert peak.qualified is False
    assert compute_psd_features(result, bands).bands[0].integrated_power_v2 is None


def test_spectrogram_uses_linear_power_and_coverage_per_window() -> None:
    # Given: dB deliberately disagrees; coverage qualifies only the first window.
    overview = SpectrogramOverview(
        power_db=np.full((2, 2), 99.0, dtype=np.float32),
        linear_power=np.array([[2.0, 8.0], [2.0, 8.0]], dtype=np.float64),
        coverage=np.array([[1, 1], [1, 0]], dtype=np.uint32),
        time_s=np.array([0.0, 1.0]),
        frequency_hz=np.array([1.5, 2.5]),
        frequency_edges_hz=np.array([1.0, 2.0, 3.0]),
        settings=StftSettings(
            version=1,
            window="hann",
            segment_samples=8,
            hop_samples=4,
            detrend="constant",
            scaling="psd",
        ),
        db_reference=1.0,
        floor_db=-200.0,
        ceiling_db=100.0,
    )
    bands = BandSet(bands=(_band(low_hz=1.0, high_hz=3.0),))

    # When
    windows = compute_spectrogram_features(overview, bands)

    # Then
    assert windows[0].bands[0].integrated_power_v2 == pytest.approx(4.0)
    assert windows[1].bands[0].integrated_power_v2 is None
    assert windows[1].bands[0].noise_floor.reason_code == "unqualified_bins"


def test_event_rate_and_duty_are_band_scoped() -> None:
    # Given: one qualified 100-sample event in a two-second capture.
    settings = event_preset("impulses_default")
    event = CandidateEvent(
        start_sample=100,
        end_sample=199,
        peak_sample=150,
        start_time_s=0.1,
        end_time_s=0.199,
        peak_time_s=0.15,
        peak_value_v=0.5,
        polarity=Polarity.POSITIVE,
        dominant_band="low",
        excess_energy_v2_s=0.01,
        snr=10.0,
        qualification_status=QualificationStatus.QUALIFIED,
        boundary=False,
        clipped=False,
    )
    inventory = EventInventory(
        schema_version=1,
        sample_rate_hz=1_000.0,
        sample_count=2_000,
        settings_hash="fixture",
        settings=settings,
        baseline_qualification_rule_id=None,
        events=(event,),
        unqualified_gaps=(),
    )

    # When
    metric = compute_event_features(inventory, feature_band_preset("lnt_working_v1")).bands[0]

    # Then
    assert metric.event_rate_hz == pytest.approx(0.5)
    assert metric.duty_cycle == pytest.approx(0.05)
    assert metric.event_count == 1


def test_peak_tracking_preserves_identity_and_ends_without_interpolation() -> None:
    # Given: a peak shifts within tolerance, then disappears.
    observations = (
        PeakObservation(window_id="w0", time_s=0.0, peaks=(QualifiedPeak("low", 10_000.0),)),
        PeakObservation(window_id="w1", time_s=1.0, peaks=(QualifiedPeak("low", 10_040.0),)),
        PeakObservation(window_id="w2", time_s=2.0, peaks=()),
    )

    # When
    tracks = track_peak_trajectories(observations, tolerance_hz=50.0)

    # Then
    assert len(tracks) == 1
    assert tracks[0].track_id == "track-0001"
    assert tuple(point.state.value for point in tracks[0].points) == (
        "observed",
        "observed",
        "unavailable",
    )
    assert tuple(point.frequency_hz for point in tracks[0].points) == (10_000.0, 10_040.0, None)
    assert tracks[0].state.value == "ended"
