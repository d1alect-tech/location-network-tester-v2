from __future__ import annotations

import csv
from dataclasses import asdict
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis import analysis_to_payload, analyze_measurement_session, write_analysis
from lnt.spectrum import compute_band_spectrum
from tests.ch1_contract_fixtures import (
    Ch1SessionSpec,
    ToneCaptureSpec,
    floating_measurement_setup,
    make_tone_captures,
    self_noise_setup,
    write_v2_session,
)

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE_RATE_HZ = 100_000.0
DURATION_S = 2.1
TONE_FREQUENCY_HZ = 9_765.625
RESISTANCE_OHM = 100.0
EQUIVALENT_CAPACITANCE_F = 5e-9


def test_input_referred_excess_psd_recovers_qualified_tone_without_changing_raw_welch(
    tmp_path: Path,
) -> None:
    # Given: a tone attenuated by the explicit CH1 transfer model plus matched self-noise.
    angular_frequency = 2.0 * np.pi * TONE_FREQUENCY_HZ
    transfer_gain = (angular_frequency * RESISTANCE_OHM * EQUIVALENT_CAPACITANCE_F) / np.sqrt(
        1.0 + (angular_frequency * RESISTANCE_OHM * EQUIVALENT_CAPACITANCE_F) ** 2,
    )
    captures = make_tone_captures(
        ToneCaptureSpec(
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            tone_frequency_hz=TONE_FREQUENCY_HZ,
            source_amplitude_v=0.2,
            transfer_gain=float(transfer_gain),
            baseline_sigma_v=0.0002,
        ),
    )
    baseline = tmp_path / "baseline"
    measurement = tmp_path / "measurement"
    write_v2_session(
        baseline,
        spec=Ch1SessionSpec(
            session_id="baseline",
            session_type="self_noise",
            source="device",
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            ch1_setup=self_noise_setup(),
            baseline_session=None,
            calibration_used=False,
        ),
        ch1=captures.scope_baseline,
        ch2=captures.ch2,
    )
    write_v2_session(
        measurement,
        spec=Ch1SessionSpec(
            session_id="measurement",
            session_type="measurement",
            source="device",
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            ch1_setup=floating_measurement_setup(),
            baseline_session="../baseline",
            calibration_used=False,
        ),
        ch1=captures.scope_measurement,
        ch2=captures.ch2,
    )
    expected_raw = compute_band_spectrum(
        captures.scope_measurement,
        sample_rate_hz=SAMPLE_RATE_HZ,
    )
    expected_baseline = compute_band_spectrum(
        captures.scope_baseline,
        sample_rate_hz=SAMPLE_RATE_HZ,
    )
    expected_source = compute_band_spectrum(captures.source, sample_rate_hz=SAMPLE_RATE_HZ)
    tone_index = int(np.argmax(expected_source.psd_v2_per_hz))
    quiet_index = int(np.argmin(expected_source.psd_v2_per_hz))

    # When: the explicit baseline is applied after raw Welch estimation.
    result = analyze_measurement_session(measurement)
    _, raw_spectrum_path = write_analysis(measurement, result)

    # Then: raw PSD/needle output remains scope-plane data, while only qualified excess is referred.
    np.testing.assert_allclose(result.spectrum.psd_v2_per_hz, expected_raw.psd_v2_per_hz)
    raw_peak = min(
        result.spectrum.peaks,
        key=lambda peak: abs(peak.frequency_hz - expected_source.frequencies_hz[tone_index]),
    )
    assert raw_peak.frequency_hz == pytest.approx(
        expected_source.frequencies_hz[tone_index],
        abs=result.spectrum.resolution_hz,
    )
    payload = analysis_to_payload(result)
    assert payload["needle"] == asdict(result.needle)
    input_reference = payload["ch1_input_reference"]
    assert isinstance(input_reference, dict)
    assert input_reference["status"] == "available"
    qualified = expected_raw.psd_v2_per_hz >= 2.0 * expected_baseline.psd_v2_per_hz
    assert qualified[tone_index]
    assert not qualified[quiet_index]

    with (measurement / "spectrum_input_referred.csv").open(encoding="utf-8", newline="") as handle:
        input_rows = tuple(csv.DictReader(handle))
    input_frequencies = np.array([float(row["frequency_hz"]) for row in input_rows])
    input_psd = np.array(
        [float(row["input_referred_excess_psd_v2_per_hz"]) for row in input_rows],
    )
    tone_row = int(
        np.argmin(np.abs(input_frequencies - expected_source.frequencies_hz[tone_index]))
    )
    assert input_psd[tone_row] == pytest.approx(
        expected_source.psd_v2_per_hz[tone_index],
        rel=0.05,
    )
    assert not np.any(
        np.isclose(input_frequencies, expected_source.frequencies_hz[quiet_index]),
    )
    assert raw_spectrum_path.read_text(encoding="utf-8").splitlines()[0] == (
        "frequency_hz,psd_v2_per_hz"
    )
