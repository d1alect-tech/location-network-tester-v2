"""Nominal loaded transfer model for the external series-C AC adapter.

Supported topology: series capacitor at the DUT end, before an x1 probe tip,
with the scope input as a nominal 1 Mohm load. The model is a one-pole
high-pass. It is nominal transfer evidence only: it does not qualify the
physical assembly, protect the input, calibrate voltage, or correct samples
back to the DUT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from typing import Final

from lnt.errors import InputError
from lnt.types import ComponentValuesBasis

TOPOLOGY_ID: Final = "series_c_at_dut_tip_x1_v1"
RIN_OHM: Final = 1_000_000.0
SETTLING_TAU_MULTIPLE: Final = 10.0
HARDWARE_QUALIFICATION: Final = "unverified"

ASSUMPTION_ONE_POLE: Final = "one_pole_nominal_transfer"
ASSUMPTION_SETTLING_POLICY: Final = "settling_policy_10_tau"
ASSUMPTION_NO_INVERSE_TRANSFER: Final = "no_inverse_transfer_correction"
ASSUMPTION_NO_PROTECTION: Final = "no_hardware_protection_guarantee"
ASSUMPTION_HARDWARE_UNVERIFIED: Final = "hardware_qualification_unverified"
ASSUMPTION_RAIL_PROVENANCE: Final = "rail_nominal_is_provenance_not_measurement"
ASSUMPTION_UNKNOWN_PROBE: Final = "probe_transfer_unavailable_unknown_topology"

_NF_TO_F: Final = Decimal("1e-9")


class TransferStatus(StrEnum):
    """Availability of the nominal adapter transfer for the declared probe."""

    NOMINAL = "nominal_transfer_declared"
    UNAVAILABLE = "unavailable_unknown_probe_topology"


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"ripple adapter: {name} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise InputError(f"ripple adapter: {name} must be finite") from exc
    if not math.isfinite(number):
        raise InputError(f"ripple adapter: {name} must be finite")
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool):
        raise InputError(f"ripple adapter: {name} must be a positive integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        number = int(value)
    else:
        raise InputError(f"ripple adapter: {name} must be a positive integer")
    if number <= 0:
        raise InputError(f"ripple adapter: {name} must be a positive integer")
    return number


def _component_basis(value: object) -> ComponentValuesBasis:
    if not isinstance(value, ComponentValuesBasis):
        raise InputError(
            "ripple adapter: component_values_basis must be nominal or operator_measured"
        )
    return value


def _tau_s(*, cap_nf: float, series_r_ohm: float) -> float:
    return (RIN_OHM + series_r_ohm) * cap_nf * 1e-9


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterSpec:
    """Nominal x1 series-C adapter at the DUT tip.

    ``rail_nominal_v`` is optional provenance, never a measurement, protection
    rating, or input to the transfer calculation. Component values are declared
    nominal or operator-measured values, not automatically detected hardware.
    ``probe_multiplier`` is a positive integer; integral float provenance is
    normalized once to int, while non-integral, nonfinite, or nonnumeric values
    raise ``InputError``.
    """

    cap_nf: float = 100.0
    series_r_ohm: float = 0.0
    probe_multiplier: int = 1
    rail_nominal_v: float | None = None
    component_values_basis: ComponentValuesBasis = ComponentValuesBasis.NOMINAL

    def __post_init__(self) -> None:
        """Rejects nonphysical or nonfinite declared model inputs."""
        cap_nf = _finite("cap_nf", self.cap_nf)
        if cap_nf <= 0.0:
            raise InputError("ripple adapter: cap_nf must be positive")
        series_r_ohm = _finite("series_r_ohm", self.series_r_ohm)
        if series_r_ohm < 0.0:
            raise InputError("ripple adapter: series_r_ohm must be nonnegative")
        probe = _positive_int("probe_multiplier", self.probe_multiplier)
        basis = _component_basis(self.component_values_basis)
        rail = self.rail_nominal_v
        if rail is not None:
            rail = _finite("rail_nominal_v", rail)
        if probe == 1:
            tau_s = _tau_s(cap_nf=cap_nf, series_r_ohm=series_r_ohm)
            if not math.isfinite(tau_s) or tau_s <= 0.0:
                raise InputError("ripple adapter: derived tau_s must be finite and positive")
            if not math.isfinite(1.0 / tau_s):
                raise InputError("ripple adapter: derived fc_hz must be finite")
            if not math.isfinite(SETTLING_TAU_MULTIPLE * tau_s):
                raise InputError("ripple adapter: derived settling_s must be finite")
        object.__setattr__(self, "cap_nf", cap_nf)
        object.__setattr__(self, "series_r_ohm", series_r_ohm)
        object.__setattr__(self, "probe_multiplier", probe)
        object.__setattr__(self, "component_values_basis", basis)
        object.__setattr__(self, "rail_nominal_v", rail)

    @property
    def topology_id(self) -> str:
        """Stable topology identifier for the sidecar."""
        return TOPOLOGY_ID

    @property
    def rin_ohm(self) -> float:
        """Nominal 1 Mohm scope input at x1; not measured."""
        return RIN_OHM

    @property
    def transfer_available(self) -> bool:
        """True only for the supported x1 physical topology."""
        return self.probe_multiplier == 1

    @property
    def transfer_status(self) -> TransferStatus:
        """Machine-readable transfer availability for the declared probe."""
        return TransferStatus.NOMINAL if self.transfer_available else TransferStatus.UNAVAILABLE

    @property
    def hardware_qualification(self) -> str:
        """Physical assembly qualification stays unverified."""
        return HARDWARE_QUALIFICATION

    @property
    def tau_s(self) -> float | None:
        """Rt*C in seconds, or None for an unsupported probe topology."""
        if not self.transfer_available:
            return None
        return _tau_s(cap_nf=self.cap_nf, series_r_ohm=self.series_r_ohm)

    @property
    def fc_hz(self) -> float | None:
        """Loaded one-pole corner, or None for an unsupported probe topology."""
        tau_s = self.tau_s
        if tau_s is None:
            return None
        return 1.0 / (2.0 * math.pi * tau_s)

    @property
    def plateau_gain(self) -> float | None:
        """High-frequency plateau Rin/(Rin+Rs), or None when unavailable."""
        if not self.transfer_available:
            return None
        return RIN_OHM / (RIN_OHM + self.series_r_ohm)

    @property
    def settling_s(self) -> float | None:
        """Nominal 10*tau settling policy, or None when unavailable."""
        tau_s = self.tau_s
        if tau_s is None:
            return None
        return SETTLING_TAU_MULTIPLE * tau_s

    @property
    def assumption_codes(self) -> tuple[str, ...]:
        """Stable machine-readable model limits for artifact provenance."""
        codes = [
            ASSUMPTION_ONE_POLE,
            f"component_values_{self.component_values_basis.value}",
            ASSUMPTION_SETTLING_POLICY,
            ASSUMPTION_NO_INVERSE_TRANSFER,
            ASSUMPTION_NO_PROTECTION,
            ASSUMPTION_HARDWARE_UNVERIFIED,
        ]
        if self.rail_nominal_v is not None:
            codes.append(ASSUMPTION_RAIL_PROVENANCE)
        if not self.transfer_available:
            codes.append(ASSUMPTION_UNKNOWN_PROBE)
        return tuple(codes)

    def gain_at(self, frequency_hz: float) -> float | None:
        """Nominal |H(f)|; no inverse correction or hardware qualification."""
        frequency = _finite("frequency_hz", frequency_hz)
        if frequency < 0.0:
            raise InputError("ripple adapter: frequency_hz must be nonnegative")
        tau_s = self.tau_s
        plateau_gain = self.plateau_gain
        if tau_s is None or plateau_gain is None:
            return None
        normalized = 2.0 * math.pi * frequency * tau_s
        if math.isinf(normalized):
            return plateau_gain
        return plateau_gain * normalized / math.hypot(1.0, normalized)

    def settle_samples(self, sample_rate_hz: float) -> int | None:
        """ceil(fs * 10*tau) from declared decimals, or None when unavailable.

        Decimal arithmetic keeps exact integer boundaries exact; binary float
        multiplication can add a phantom sample (for example Rs=1 kohm at
        fs=1000 would otherwise ceil to 1002 instead of 1001).
        """
        sample_rate = _finite("sample_rate_hz", sample_rate_hz)
        if sample_rate <= 0.0:
            raise InputError("ripple adapter: sample_rate_hz must be positive")
        if not self.transfer_available:
            return None
        cap_f = Decimal(str(self.cap_nf)) * _NF_TO_F
        rt_ohm = Decimal(str(RIN_OHM)) + Decimal(str(self.series_r_ohm))
        settle_s = Decimal(str(SETTLING_TAU_MULTIPLE)) * rt_ohm * cap_f
        samples = Decimal(str(sample_rate)) * settle_s
        return int(samples.to_integral_value(rounding=ROUND_CEILING))

    def step_residual_at_settling_v(self, step_v: float) -> float | None:
        """Ideal step residual at 10*tau; a model value, not protection."""
        step = _finite("step_v", step_v)
        plateau_gain = self.plateau_gain
        if plateau_gain is None:
            return None
        return step * plateau_gain * math.exp(-SETTLING_TAU_MULTIPLE)
