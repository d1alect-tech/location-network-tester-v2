"""Настройка входа CH1 для захвата (чистые помощники).

Выделено из ``lnt.acquire`` без изменения семантики: выбор и значение
по умолчанию дискриминированного ``ch1_setup``, множитель пробника,
метаданные канала и front-end профиль для коллектора метаданных.
Лист: импортирует только scope/profile/metadata-хелперы, никогда ``acquire``.
"""

from lnt.errors import InputError
from lnt.profiles import FrontEndProfile
from lnt.types import (
    Ch1Setup,
    ChannelMeta,
    ChannelRole,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)

__all__ = [
    "DEFAULT_TERMINATION_OHM",
    "DEFAULT_TRANSFORMER_PRIMARY_V",
    "DEFAULT_TRANSFORMER_PROBE_MULTIPLIER",
    "DEFAULT_TRANSFORMER_SECONDARY_V",
    "FRONT_END_CH1",
    "FRONT_END_CH2",
    "Ch1Setup",
    "_capture_setup",
    "_ch1_meta",
    "_ch1_probe_multiplier",
    "_default_setup",
    "_metadata_front_end",
]

FRONT_END_CH1 = "x2-probe 2x10nF+100R"
FRONT_END_CH2 = "transformer 230:6"
DEFAULT_TERMINATION_OHM = 50.0
DEFAULT_TRANSFORMER_PRIMARY_V = 230.0
DEFAULT_TRANSFORMER_SECONDARY_V = 6.0
DEFAULT_TRANSFORMER_PROBE_MULTIPLIER = 10.0


def _metadata_front_end(setup: Ch1Setup) -> FrontEndProfile:
    match setup:
        case FloatingDifferentialRcShunt(
            resistance_ohm=resistance,
            c1_f=c1,
            c2_f=c2,
        ):
            return FrontEndProfile.from_si(resistance_ohm=resistance, c1_f=c1, c2_f=c2)
        case ScopeInputTerminated(termination_resistance_ohm=resistance):
            return FrontEndProfile.from_si(resistance_ohm=resistance, c1_f=1e-30, c2_f=1e-30)
        case TransformerLineProbe():
            return FrontEndProfile.from_si(resistance_ohm=1.0, c1_f=1e-30, c2_f=1e-30)


def _capture_setup(*, session_type: SessionType, setup: Ch1Setup | None) -> Ch1Setup:
    selected = setup if setup is not None else _default_setup(session_type)
    match session_type, selected:
        case SessionType.MEASUREMENT, FloatingDifferentialRcShunt():
            return selected
        case SessionType.SELF_NOISE, ScopeInputTerminated():
            return selected
        case SessionType.LINE_QUALITY, TransformerLineProbe():
            return selected
        case _:
            raise InputError("ch1_setup не соответствует назначению capture-сессии")


def _default_setup(session_type: SessionType) -> Ch1Setup:
    match session_type:
        case SessionType.MEASUREMENT | SessionType.CM_DM | SessionType.CM_DM_CALIBRATION:
            return FloatingDifferentialRcShunt(
                resistance_ohm=100.0,
                c1_f=10e-9,
                c2_f=10e-9,
                component_values_basis=ComponentValuesBasis.NOMINAL,
                reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
            )
        case SessionType.SELF_NOISE:
            return ScopeInputTerminated(termination_resistance_ohm=DEFAULT_TERMINATION_OHM)
        case SessionType.LINE_QUALITY:
            return TransformerLineProbe(
                nominal_primary_v=DEFAULT_TRANSFORMER_PRIMARY_V,
                nominal_secondary_v=DEFAULT_TRANSFORMER_SECONDARY_V,
                probe_multiplier=DEFAULT_TRANSFORMER_PROBE_MULTIPLIER,
            )


def _ch1_probe_multiplier(setup: Ch1Setup) -> float:
    match setup:
        case TransformerLineProbe():
            return setup.probe_multiplier
        case _:
            return 1.0


def _ch1_meta(setup: Ch1Setup, *, range_code: int) -> ChannelMeta:
    match setup:
        case TransformerLineProbe():
            return ChannelMeta(
                filename="ch1.npy",
                role=ChannelRole.LF_TRANSFORMER,
                unit="V",
                front_end=FRONT_END_CH2,
                range_code=range_code,
                probe_multiplier=setup.probe_multiplier,
            )
        case _:
            return ChannelMeta(
                filename="ch1.npy",
                role=ChannelRole.HF_PROBE,
                unit="V",
                front_end=FRONT_END_CH1,
                range_code=range_code,
                probe_multiplier=1.0,
            )
