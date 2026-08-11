from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.settings import WelchSettings
from lnt.events import DetectionSettings, detect_events
from lnt.events import FrequencyBand as EventBand
from lnt.features import (
    BandDefinition,
    BandSet,
    EstimandDirection,
    FrequencyUnit,
    compute_psd_features,
)
from lnt.line_quality_v2 import compute_line_quality_v2
from lnt.psd import FrequencyBand, PsdSettings, compute_welch
from lnt.spectrogram import StftSettings, build_overview
from tests.science.corpus import drift, impulses, pure_tone
from tests.science.truth import TruthMismatchError, verify_scalar

if TYPE_CHECKING:
    from pathlib import Path


def _psd_settings(rate_hz: float) -> PsdSettings:
    recipe = WelchSettings(
        window="hann_periodic",
        segment_samples=2_048,
        overlap_fraction=0.5,
        detrend="constant",
        scaling="density",
        average="mean",
    )
    return PsdSettings.from_recipe(
        sample_rate_hz=rate_hz,
        welch=recipe,
        bands=(FrequencyBand(name="all", low_hz=0.0, high_hz=rate_hz / 2),),
    )


def _event_settings(rate_hz: float) -> DetectionSettings:
    return DetectionSettings(
        event_detection_version=1,
        preset_name="science",
        noise_window_samples=501,
        noise_step_samples=64,
        minimum_noise_samples=250,
        threshold_sigma=6.0,
        max_gap_samples=8,
        minimum_event_samples=1,
        minimum_snr=6.0,
        chunk_samples=2_048,
        rail_low_v=-1.0,
        rail_high_v=1.0,
        rail_tolerance_v=1e-6,
        bands=(EventBand(name="all", low_hz=0.0, high_hz=rate_hz / 2),),
    )


def test_psd_peak_and_features_match_independent_tone_truth() -> None:
    fixture = pure_tone()
    result = compute_welch(fixture.samples, settings=_psd_settings(fixture.sample_rate_hz))
    peak_hz = float(result.frequency_hz[np.argmax(result.psd_v2_per_hz)])
    verify_scalar(
        peak_hz,
        expected=fixture.truth.peak_hz or 0.0,
        absolute_tolerance=8.0,
        rationale=fixture.truth.tolerance_rationale,
    )
    bands = BandSet(
        bands=(
            BandDefinition(
                name="tone",
                low=900,
                high=1_100,
                unit=FrequencyUnit.HZ,
                direction=EstimandDirection.HIGHER,
            ),
        )
    )
    feature = compute_psd_features(result, bands).bands[0]
    assert feature.integrated_power_v2 == pytest.approx(fixture.truth.band_power_v2, rel=0.01)


def test_spectrogram_overview_localizes_tone(tmp_path: Path) -> None:
    fixture = pure_tone()
    path = tmp_path / "tone.npy"
    np.save(path, fixture.samples, allow_pickle=False)
    overview = build_overview(
        path,
        sample_rate_hz=fixture.sample_rate_hz,
        settings=StftSettings(
            version=1,
            window="hann",
            segment_samples=2_048,
            hop_samples=1_024,
            detrend="constant",
            scaling="psd",
        ),
        max_time_bins=8,
        max_frequency_bands=64,
        band_low_hz=64.0,
        band_high_hz=8_192.0,
    )
    sums = np.nansum(overview.linear_power, axis=1)
    peak_hz = float(overview.frequency_hz[np.argmax(sums)])
    verify_scalar(
        peak_hz,
        expected=fixture.truth.peak_hz or 0.0,
        absolute_tolerance=50.0,
        rationale="Log-frequency overview cell width near 1 kHz is 78 Hz.",
    )


def test_event_engine_recovers_seeded_impulse_times() -> None:
    fixture = impulses()
    rng = np.random.default_rng(fixture.seed)
    samples = fixture.samples.astype(np.float64) + rng.normal(0.0, 0.005, fixture.samples.size)
    inventory = detect_events(
        samples,
        sample_rate_hz=fixture.sample_rate_hz,
        settings=_event_settings(fixture.sample_rate_hz),
    )
    detected = tuple(event.peak_sample for event in inventory.events)
    assert detected == fixture.truth.event_samples


def test_line_quality_v2_tracks_frequency_drift() -> None:
    fixture = drift()
    result = compute_line_quality_v2(fixture.samples, sample_rate_hz=fixture.sample_rate_hz)
    verify_scalar(
        result.metrics.fundamental_hz,
        expected=fixture.truth.peak_hz or 0.0,
        absolute_tolerance=0.6,
        rationale=fixture.truth.tolerance_rationale,
    )


def test_peak_mutation_is_rejected_by_shared_verifier() -> None:
    fixture = pure_tone()
    with pytest.raises(TruthMismatchError):
        verify_scalar(
            (fixture.truth.peak_hz or 0.0) + 16.0,
            expected=fixture.truth.peak_hz or 0.0,
            absolute_tolerance=8.0,
            rationale=fixture.truth.tolerance_rationale,
        )
