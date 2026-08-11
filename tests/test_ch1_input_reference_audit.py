from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis import analysis_to_payload, analyze_measurement_session
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
TONE_FREQUENCY_HZ = 9_750.0


def _qualified_measurement(root: Path) -> Path:
    angular_frequency = 2.0 * math.pi * TONE_FREQUENCY_HZ
    transfer_gain = (angular_frequency * 100.0 * 5e-9) / math.sqrt(
        1.0 + (angular_frequency * 100.0 * 5e-9) ** 2,
    )
    captures = make_tone_captures(
        ToneCaptureSpec(
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            tone_frequency_hz=TONE_FREQUENCY_HZ,
            source_amplitude_v=1.0,
            transfer_gain=transfer_gain,
            baseline_sigma_v=0.00002,
        ),
    )
    write_v2_session(
        root / "baseline",
        spec=Ch1SessionSpec(
            session_id="baseline",
            session_type="self_noise",
            source="device",
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            ch1_setup=self_noise_setup(),
            baseline_session=None,
        ),
        ch1=captures.scope_baseline,
        ch2=captures.ch2,
    )
    measurement = root / "measurement"
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
        ),
        ch1=captures.scope_measurement,
        ch2=captures.ch2,
    )
    return measurement


def test_input_reference_payload_emits_complete_model_and_baseline_provenance(
    tmp_path: Path,
) -> None:
    # Given: a qualified floating-RC measurement and explicit self-noise baseline.
    result = analyze_measurement_session(_qualified_measurement(tmp_path))

    # When: the public analysis payload is assembled.
    payload = analysis_to_payload(result)

    # Then: machine consumers receive the model, rule, counts, baseline, and corrected peaks.
    reference = payload["ch1_input_reference"]
    assert isinstance(reference, dict)
    assert reference["baseline_session_id"] == "baseline"
    assert reference["qualification_rule_id"] == "measurement_psd_gte_2x_baseline_psd_v1"
    assert reference["qualified_bin_count"] > 0
    assert reference["total_bin_count"] > reference["qualified_bin_count"]
    model = reference["model"]
    assert isinstance(model, dict)
    assert model == {
        "kind": "floating_differential_rc_shunt_v1",
        "resistance_ohm": 100.0,
        "c1_f": 10e-9,
        "c2_f": 10e-9,
        "component_values_basis": "nominal",
        "reference_assumption": "floating_host_unverified",
    }
    corrected_peaks = reference["corrected_peaks"]
    assert isinstance(corrected_peaks, list)
    assert corrected_peaks
    first_peak = corrected_peaks[0]
    assert isinstance(first_peak, dict)
    assert first_peak["frequency_hz"] == pytest.approx(
        TONE_FREQUENCY_HZ,
        abs=result.spectrum.resolution_hz,
    )


def test_input_reference_keeps_unqualified_aligned_bins_absent(tmp_path: Path) -> None:
    # Given: a qualified measurement with bins below the explicit 2x baseline rule.
    reference = analyze_measurement_session(_qualified_measurement(tmp_path)).ch1_input_reference

    # When: corrected excess PSD is retained in its aligned in-memory spectrum.
    # Then: unqualified bins are absent-like, never hidden finite corrected noise.
    assert reference.input_referred_excess_psd_v2_per_hz is not None
    assert reference.qualified is not None
    assert np.any(reference.qualified)
    assert np.any(~reference.qualified)
    assert np.all(np.isnan(reference.input_referred_excess_psd_v2_per_hz[~reference.qualified]))
