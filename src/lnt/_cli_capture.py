"""Аргументы ``lnt capture`` для явного CH1 transfer/setup provenance."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from lnt.errors import InputError
from lnt.types import (
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)

DEFAULT_RC_R_OHM = 100.0
DEFAULT_RC_C_NF = 10.0
DEFAULT_TERMINATION_OHM = 50.0
DEFAULT_TRANSFORMER_PRIMARY_V = 230.0
DEFAULT_TRANSFORMER_SECONDARY_V = 6.0
DEFAULT_TRANSFORMER_PROBE_MULTIPLIER = 10.0
RC_COMPONENT_COUNT = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureSetupOptions:
    """Явные CLI-вводы CH1 setup до их преобразования в доменную модель."""

    baseline_session: str | None
    resistance_ohm: float | None
    c1_nf: float | None
    c2_nf: float | None
    component_values_basis: str | None
    termination_ohm: float | None
    probe_multiplier: float | None = None


def add_capture_arguments(
    parser: argparse.ArgumentParser,
    *,
    finite_float: Callable[[str], float],
) -> None:
    """Добавляет capture-флаги, не меняя общий parser/exit-контракт CLI."""
    parser.add_argument("--out", required=True, help="каталог новой сессии")
    parser.add_argument("--duration", type=finite_float, default=2.4)
    parser.add_argument("--rate", type=finite_float, default=8_000_000.0)
    parser.add_argument(
        "--range",
        type=finite_float,
        choices=[5.0, 1.0, 0.5],
        default=5.0,
        dest="range_v",
        help="диапазон CH1, В: 5 | 1 | 0.5 (полная шкала +-5.12/+-1.024/+-0.512 В)",
    )
    parser.add_argument(
        "--self-noise",
        action="store_true",
        dest="self_noise",
        help="baseline самошума: фронтенды отключены, входы терминированы",
    )
    parser.add_argument(
        "--line-quality",
        action="store_true",
        dest="line_quality",
        help="качество сети 50 Гц: CH1 = вторичка трансформатора 230:6 (одноканальный)",
    )
    parser.add_argument(
        "--probe-multiplier",
        type=finite_float,
        default=None,
        dest="probe_multiplier",
        help="коэффициент пробника для --line-quality (по умолчанию 10 — пробник 10x)",
    )
    parser.add_argument("--baseline", default=None, help="явный каталог baseline self-noise")
    parser.add_argument("--rc-r-ohm", type=finite_float, default=None)
    parser.add_argument("--rc-c1-nf", type=finite_float, default=None)
    parser.add_argument("--rc-c2-nf", type=finite_float, default=None)
    parser.add_argument(
        "--component-values-basis",
        choices=[basis.value for basis in ComponentValuesBasis],
        default=None,
    )
    parser.add_argument("--termination-ohm", type=finite_float, default=None)


def build_capture_setup(
    *,
    session_type: SessionType,
    options: CaptureSetupOptions,
) -> FloatingDifferentialRcShunt | ScopeInputTerminated | TransformerLineProbe:
    """Преобразует явные CLI flags в совместимую с capture-сессией CH1 setup."""
    match session_type:
        case SessionType.MEASUREMENT:
            if options.termination_ohm is not None:
                raise InputError("--termination-ohm допустим только для --self-noise")
            if options.probe_multiplier is not None:
                raise InputError("--probe-multiplier допустим только для --line-quality")
            return _measurement_setup(options)
        case SessionType.SELF_NOISE:
            if _has_measurement_only_option(options) or options.probe_multiplier is not None:
                raise InputError("--self-noise не принимает --baseline или measurement flags")
            return ScopeInputTerminated(
                termination_resistance_ohm=(
                    options.termination_ohm
                    if options.termination_ohm is not None
                    else DEFAULT_TERMINATION_OHM
                ),
            )
        case SessionType.LINE_QUALITY:
            if _has_measurement_only_option(options) or options.termination_ohm is not None:
                raise InputError(
                    "--line-quality не принимает --baseline, RC или termination flags",
                )
            return TransformerLineProbe(
                nominal_primary_v=DEFAULT_TRANSFORMER_PRIMARY_V,
                nominal_secondary_v=DEFAULT_TRANSFORMER_SECONDARY_V,
                probe_multiplier=(
                    options.probe_multiplier
                    if options.probe_multiplier is not None
                    else DEFAULT_TRANSFORMER_PROBE_MULTIPLIER
                ),
            )


def _measurement_setup(options: CaptureSetupOptions) -> FloatingDifferentialRcShunt:
    components = (options.resistance_ohm, options.c1_nf, options.c2_nf)
    component_count = sum(value is not None for value in components)
    if component_count == 0:
        if options.component_values_basis is not None:
            raise InputError("--component-values-basis требует полный RC triplet")
        return FloatingDifferentialRcShunt(
            resistance_ohm=DEFAULT_RC_R_OHM,
            c1_f=DEFAULT_RC_C_NF * 1e-9,
            c2_f=DEFAULT_RC_C_NF * 1e-9,
            component_values_basis=ComponentValuesBasis.NOMINAL,
            reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
        )
    if component_count != RC_COMPONENT_COUNT:
        raise InputError("RC overrides требуют --rc-r-ohm, --rc-c1-nf и --rc-c2-nf вместе")
    if options.component_values_basis == ComponentValuesBasis.NOMINAL.value:
        raise InputError("явный RC triplet не может иметь nominal basis")
    match components:
        case (float() as resistance_ohm, float() as c1_nf, float() as c2_nf):
            return FloatingDifferentialRcShunt(
                resistance_ohm=resistance_ohm,
                c1_f=c1_nf * 1e-9,
                c2_f=c2_nf * 1e-9,
                component_values_basis=ComponentValuesBasis.OPERATOR_MEASURED,
                reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
            )
        case _:
            raise InputError("RC overrides должны быть конечными числами")


def _has_measurement_only_option(options: CaptureSetupOptions) -> bool:
    return any(
        value is not None
        for value in (
            options.baseline_session,
            options.resistance_ohm,
            options.c1_nf,
            options.c2_nf,
            options.component_values_basis,
        )
    )
