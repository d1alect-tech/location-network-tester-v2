from __future__ import annotations

from importlib import import_module

import pytest


def test_floating_rc_transfer_corrects_amplitude_and_psd_at_band_edges() -> None:
    # Given: the documented floating differential 2x10 nF / 100 Ohm CH1 model.
    input_reference = import_module("lnt.input_reference")
    model = input_reference.FloatingDifferentialRcShunt(
        resistance_ohm=100.0,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis="nominal",
        reference_assumption="floating_host_unverified",
    )

    # When: transfer correction is evaluated at both boundaries of the CH1 band.
    low = model.correction_at(frequency_hz=3_000.0)
    high = model.correction_at(frequency_hz=3_000_000.0)

    # Then: the series-equivalent capacitance and amplitude/power corrections are exact.
    assert low.equivalent_capacitance_f == pytest.approx(5e-9)
    assert low.amplitude_gain == pytest.approx(0.009424359, rel=1e-7)
    assert high.amplitude_gain == pytest.approx(0.994418, rel=1e-6)
    assert low.input_amplitude(scope_amplitude_v=0.02) == pytest.approx(
        0.02 / low.amplitude_gain,
    )
    assert low.input_psd(scope_psd_v2_per_hz=2e-12) == pytest.approx(
        2e-12 / low.amplitude_gain**2,
    )
