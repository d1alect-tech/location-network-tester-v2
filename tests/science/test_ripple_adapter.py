"""Analytic checks for the external series-C AC adapter nominal transfer model.

Truth is closed-form: one-pole high-pass with the loaded 1 Mohm scope input,
not engine output. The model is nominal transfer only; it is not hardware
qualification, calibration, protection, or an inverse correction.
"""

from __future__ import annotations

import math

import pytest

from lnt.errors import InputError
from lnt.ripple.adapter import RIN_OHM, TOPOLOGY_ID, AdapterSpec, TransferStatus
from lnt.types import ComponentValuesBasis


def _expected_gain(*, frequency_hz: float, tau_s: float, plateau_gain: float) -> float:
    """Closed-form |H(f)| for the loaded one-pole high-pass."""
    normalized = 2.0 * math.pi * frequency_hz * tau_s
    return plateau_gain * normalized / math.sqrt(1.0 + normalized * normalized)


def test_default_spec_declares_supported_topology() -> None:
    """Default preset is 100 nF, Rs=0, x1, nominal component values."""
    spec = AdapterSpec()
    assert spec.topology_id == TOPOLOGY_ID
    assert spec.rin_ohm == RIN_OHM
    assert spec.cap_nf == 100.0
    assert spec.series_r_ohm == 0.0
    assert spec.probe_multiplier == 1
    assert spec.rail_nominal_v is None
    assert spec.component_values_basis is ComponentValuesBasis.NOMINAL
    assert spec.transfer_status is TransferStatus.NOMINAL
    assert spec.transfer_available is True
    assert spec.hardware_qualification == "unverified"


def test_100nf_rs0_matches_closed_form_pole() -> None:
    """100 nF / 1 Mohm: tau 0.1 s, fc 1/(2*pi*0.1), nominal settling 1 s."""
    spec = AdapterSpec(cap_nf=100.0, series_r_ohm=0.0)
    tau_expected = 0.1
    fc_expected = 1.0 / (2.0 * math.pi * tau_expected)
    assert spec.tau_s == pytest.approx(tau_expected, rel=1e-15)
    assert spec.fc_hz == pytest.approx(fc_expected, rel=1e-15)
    assert spec.plateau_gain == pytest.approx(1.0, rel=1e-15)
    assert spec.settling_s == pytest.approx(1.0, rel=1e-15)


def test_gain_at_10hz_matches_closed_form() -> None:
    """|H(10 Hz)| = w/sqrt(1+w^2) with w = 2*pi*10*0.1."""
    spec = AdapterSpec(cap_nf=100.0, series_r_ohm=0.0)
    expected = _expected_gain(frequency_hz=10.0, tau_s=0.1, plateau_gain=1.0)
    assert spec.gain_at(10.0) == pytest.approx(expected, rel=1e-15)
    assert spec.gain_at(10.0) == pytest.approx(0.9875704921513918, rel=1e-15)


def test_gain_at_zero_is_zero() -> None:
    """A series capacitor blocks DC: |H(0)| is exactly zero."""
    spec = AdapterSpec()
    assert spec.gain_at(0.0) == 0.0


def test_1uf_matches_closed_form_pole_and_settling() -> None:
    """1 uF / 1 Mohm: tau 1 s, fc 1/(2*pi) Hz, nominal settling 10 s."""
    spec = AdapterSpec(cap_nf=1000.0, series_r_ohm=0.0)
    tau_expected = 1.0
    fc_expected = 1.0 / (2.0 * math.pi * tau_expected)
    assert spec.tau_s == pytest.approx(tau_expected, rel=1e-15)
    assert spec.fc_hz == pytest.approx(fc_expected, rel=1e-15)
    assert spec.settling_s == pytest.approx(10.0, rel=1e-15)


def test_series_1000_ohm_sets_plateau_and_pole() -> None:
    """Rs=1 kohm loads the divider: plateau Rin/(Rin+Rs) and Rt=Rin+Rs."""
    spec = AdapterSpec(cap_nf=100.0, series_r_ohm=1000.0)
    rt_ohm = RIN_OHM + 1000.0
    plateau_expected = RIN_OHM / rt_ohm
    tau_expected = rt_ohm * 100e-9
    fc_expected = 1.0 / (2.0 * math.pi * tau_expected)
    assert spec.plateau_gain == pytest.approx(plateau_expected, rel=1e-15)
    assert spec.tau_s == pytest.approx(tau_expected, rel=1e-14)
    assert spec.fc_hz == pytest.approx(fc_expected, rel=1e-14)
    expected_gain = _expected_gain(
        frequency_hz=10.0,
        tau_s=tau_expected,
        plateau_gain=plateau_expected,
    )
    assert spec.gain_at(10.0) == pytest.approx(expected_gain, rel=1e-14)


@pytest.mark.parametrize("cap_nf", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_invalid_capacitance_is_rejected(cap_nf: float) -> None:
    """Capacitance must be finite and positive."""
    with pytest.raises(InputError):
        AdapterSpec(cap_nf=cap_nf)


@pytest.mark.parametrize("series_r_ohm", [-1.0, math.nan, math.inf, -math.inf])
def test_invalid_series_resistance_is_rejected(series_r_ohm: float) -> None:
    """Series resistance must be finite and nonnegative; zero is valid."""
    with pytest.raises(InputError):
        AdapterSpec(series_r_ohm=series_r_ohm)


@pytest.mark.parametrize(
    "probe_multiplier",
    [0, -1, True, False, 1.5, 2.5, math.nan, math.inf, -math.inf, "1", None],
)
def test_invalid_probe_multiplier_is_rejected(probe_multiplier: object) -> None:
    """Probe multiplier is a positive integer provenance value."""
    with pytest.raises(InputError):
        AdapterSpec(probe_multiplier=probe_multiplier)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(("raw", "expected"), [(1.0, 1), (10.0, 10)])
def test_integral_float_probe_multiplier_is_normalized(raw: float, expected: int) -> None:
    """Integral float provenance is parsed to int; non-integral floats fail above."""
    spec = AdapterSpec(probe_multiplier=raw)  # pyright: ignore[reportArgumentType]
    assert spec.probe_multiplier == expected
    assert repr(spec.probe_multiplier) == str(expected)
    assert spec.transfer_available is (expected == 1)


@pytest.mark.parametrize("rail_nominal_v", [math.nan, math.inf, -math.inf])
def test_invalid_rail_nominal_is_rejected(rail_nominal_v: float) -> None:
    """Rail nominal provenance, when supplied, must be finite."""
    with pytest.raises(InputError):
        AdapterSpec(rail_nominal_v=rail_nominal_v)


@pytest.mark.parametrize("field_name", ["cap_nf", "series_r_ohm", "rail_nominal_v"])
def test_huge_integer_constructor_fields_raise_input_error(field_name: str) -> None:
    """Arbitrary-precision ints that overflow float are typed input failures."""
    kwargs: dict[str, object] = {field_name: 10**400}
    with pytest.raises(InputError):
        AdapterSpec(**kwargs)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    "method_name",
    ["settle_samples", "gain_at", "step_residual_at_settling_v"],
)
def test_huge_integer_method_inputs_raise_input_error(method_name: str) -> None:
    """Arbitrary-precision ints that overflow float are typed input failures."""
    method = getattr(AdapterSpec(), method_name)
    with pytest.raises(InputError):
        method(10**400)


@pytest.mark.parametrize("component_values_basis", ["nominal", "operator_measured", 1, None])
def test_invalid_component_values_basis_is_rejected(component_values_basis: object) -> None:
    """Component basis is a typed enum, not an arbitrary runtime value."""
    with pytest.raises(InputError):
        AdapterSpec(component_values_basis=component_values_basis)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("sample_rate_hz", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_settle_samples_rejects_invalid_sample_rate(sample_rate_hz: float) -> None:
    """Sample rate must be finite and positive even when transfer is unavailable."""
    spec = AdapterSpec()
    with pytest.raises(InputError):
        spec.settle_samples(sample_rate_hz)


@pytest.mark.parametrize(
    ("cap_nf", "series_r_ohm", "sample_rate_hz", "expected"),
    [
        (100.0, 0.0, 1000.0, 1000),
        (100.0, 0.0, 10_000_000.0, 10_000_000),
        (100.0, 0.0, 3.0, 3),
        (1000.0, 0.0, 10.0, 100),
        (100.0, 1000.0, 1000.0, 1001),
        (100.0, 1000.0, 10_000.0, 10_010),
        (100.0, 1000.0, 7.0, 8),
    ],
)
def test_settle_samples_rounds_ceiling_at_exact_integer_boundaries(
    cap_nf: float,
    series_r_ohm: float,
    sample_rate_hz: float,
    expected: int,
) -> None:
    """ceil(fs * 10*tau) must not add a sample from binary float noise."""
    spec = AdapterSpec(cap_nf=cap_nf, series_r_ohm=series_r_ohm)
    assert spec.settle_samples(sample_rate_hz) == expected


def test_x10_probe_does_not_infer_transfer_or_rescale() -> None:
    """Unknown x10 topology leaves transfer and settling unavailable."""
    spec = AdapterSpec(probe_multiplier=10)
    assert spec.probe_multiplier == 10
    assert spec.transfer_status is TransferStatus.UNAVAILABLE
    assert spec.transfer_available is False
    assert spec.fc_hz is None
    assert spec.tau_s is None
    assert spec.plateau_gain is None
    assert spec.settling_s is None
    assert spec.gain_at(10.0) is None
    assert spec.settle_samples(1000.0) is None
    assert spec.step_residual_at_settling_v(12.0) is None
    assert "probe_transfer_unavailable_unknown_topology" in spec.assumption_codes
    with pytest.raises(InputError):
        spec.settle_samples(0.0)


def test_negative_or_nonfinite_gain_frequency_is_rejected() -> None:
    """Requested gain frequency is a finite nonnegative physical frequency."""
    spec = AdapterSpec()
    for frequency_hz in (-1.0, math.nan, math.inf, -math.inf):
        with pytest.raises(InputError):
            spec.gain_at(frequency_hz)


def test_step_residual_at_settling_is_model_not_protection() -> None:
    """Ideal 12 V step leaves DeltaV*plateau*exp(-10) after the 10*tau policy."""
    spec = AdapterSpec(rail_nominal_v=12.0)
    expected = 12.0 * math.exp(-10.0)
    residual = spec.step_residual_at_settling_v(12.0)
    assert residual is not None
    assert residual == pytest.approx(expected, rel=1e-15)
    assert residual > 0.0
    assert spec.step_residual_at_settling_v(1.0) == pytest.approx(math.exp(-10.0))
    assert spec.hardware_qualification == "unverified"


def test_series_resistance_changes_step_residual_through_plateau() -> None:
    """The step residual uses the loaded plateau, not Rin alone."""
    spec = AdapterSpec(series_r_ohm=1000.0)
    plateau = RIN_OHM / (RIN_OHM + 1000.0)
    expected = 12.0 * plateau * math.exp(-10.0)
    assert spec.step_residual_at_settling_v(12.0) == pytest.approx(expected, rel=1e-15)


def test_operator_measured_basis_is_preserved() -> None:
    """Component-value provenance survives normalization and assumption codes."""
    spec = AdapterSpec(component_values_basis=ComponentValuesBasis.OPERATOR_MEASURED)
    assert spec.component_values_basis is ComponentValuesBasis.OPERATOR_MEASURED
    assert "component_values_operator_measured" in spec.assumption_codes
