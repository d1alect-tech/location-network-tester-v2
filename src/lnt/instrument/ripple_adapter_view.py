"""Провенанс живого адаптера риппла: номинальный preset и вид события.

Перенос из ``ripple_types`` (модуль типов превысил 250 чистых LOC). Номинальный
adapter preset — ДОПУЩЕНИЕ живого тракта (100 нФ, Rs=0, x1), а не обнаруженное
железо; для неподдерживаемого пробника перенос и окно установления честно
недоступны.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from lnt.errors import InputError
from lnt.ripple.adapter import (
    ASSUMPTION_UNKNOWN_PROBE,
    HARDWARE_QUALIFICATION,
    TOPOLOGY_ID,
    AdapterSpec,
    TransferStatus,
)
from lnt.types import ComponentValuesBasis

DEFAULT_CAP_NF: Final = 100.0
DEFAULT_SERIES_R_OHM: Final = 0.0


@dataclass(frozen=True, slots=True, kw_only=True)
class RippleAdapterView:
    """Провенанс адаптера в каждом событии: параметры и честная доступность."""

    topology_id: str
    cap_nf: float
    series_r_ohm: float
    probe_multiplier: float
    component_values_basis: str
    hardware_qualification: str
    transfer_status: str
    rail_nominal_v: float | None
    tau_s: float | None
    fc_hz: float | None
    settling_s: float | None
    settle_samples: int | None
    assumption_codes: tuple[str, ...]


def build_adapter_view(
    adapter: AdapterSpec | None,
    *,
    probe_multiplier: float,
    sample_rate_hz: float,
) -> RippleAdapterView:
    """Собирает провенанс; ``None`` — множитель не выражается x1-топологией."""
    if adapter is None:
        return RippleAdapterView(
            topology_id=TOPOLOGY_ID,
            cap_nf=DEFAULT_CAP_NF,
            series_r_ohm=DEFAULT_SERIES_R_OHM,
            probe_multiplier=probe_multiplier,
            component_values_basis=ComponentValuesBasis.NOMINAL.value,
            hardware_qualification=HARDWARE_QUALIFICATION,
            transfer_status=TransferStatus.UNAVAILABLE.value,
            rail_nominal_v=None,
            tau_s=None,
            fc_hz=None,
            settling_s=None,
            settle_samples=None,
            assumption_codes=(ASSUMPTION_UNKNOWN_PROBE,),
        )
    return RippleAdapterView(
        topology_id=adapter.topology_id,
        cap_nf=adapter.cap_nf,
        series_r_ohm=adapter.series_r_ohm,
        probe_multiplier=float(adapter.probe_multiplier),
        component_values_basis=adapter.component_values_basis.value,
        hardware_qualification=adapter.hardware_qualification,
        transfer_status=adapter.transfer_status.value,
        rail_nominal_v=adapter.rail_nominal_v,
        tau_s=adapter.tau_s,
        fc_hz=adapter.fc_hz,
        settling_s=adapter.settling_s,
        settle_samples=adapter.settle_samples(sample_rate_hz),
        assumption_codes=adapter.assumption_codes,
    )


def default_adapter(probe_multiplier: float) -> AdapterSpec | None:
    """Собирает номинальный preset 100 нФ/Rs0; нецелый пробник — ``None``."""
    if not math.isfinite(probe_multiplier) or probe_multiplier <= 0.0:
        raise InputError("риппл: множитель пробника должен быть конечным и > 0")
    if not probe_multiplier.is_integer():
        return None
    return AdapterSpec(
        cap_nf=DEFAULT_CAP_NF,
        series_r_ohm=DEFAULT_SERIES_R_OHM,
        probe_multiplier=int(probe_multiplier),
    )
