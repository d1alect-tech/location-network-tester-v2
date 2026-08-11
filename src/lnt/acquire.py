"""Сборка device-сессии: валидация входа, манифест, масштабирование raw -> В.

I/O с устройством (протокол драйвера, цикл захвата, телеметрия) — в
``scope_io``. Калибровочная поправка не применяется
(``calibration_used=False``): протокол LNT сравнивает дельты, не абсолюты.
"""

import math
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.manifest import validated_label
from lnt.metadata_collector import AcquisitionSettings, MetadataCollector
from lnt.profiles import FrontEndProfile
from lnt.scope_io import RANGE_CODE_5V, ScopeProtocol, open_real_scope, run_capture
from lnt.session_projection import index_session, write_initial_context
from lnt.session_store import write_session
from lnt.types import (
    CH1_MANIFEST_SCHEMA_VERSION,
    Ch1Setup,
    ChannelMeta,
    ChannelMode,
    ChannelRole,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ParameterValue,
    ReferenceAssumption,
    ScopeInputTerminated,
    SeriesPosition,
    SessionManifest,
    SessionSource,
    SessionType,
    TransformerLineProbe,
)

Float32Array = NDArray[np.float32]

DEFAULT_SAMPLE_RATE_HZ = 8_000_000.0
MAX_DUAL_RATE_MHZ = 15
MEGA = 1_000_000
DEFAULT_RANGE_V = 5.0
# Номинал диапазона CH1 (В) -> код гейна драйвера; полная шкала = +-5.12/код В.
RANGE_CODES: dict[float, int] = {5.0: 1, 1.0: 5, 0.5: 10}
ADC_CENTER = 128.0
VOLTS_SCALE = 5.12
FRONT_END_CH1 = "x2-probe 2x10nF+100R"
FRONT_END_CH2 = "transformer 230:6"
LINE_FREQUENCY_HZ = 50.0
DEFAULT_TERMINATION_OHM = 50.0
DEFAULT_TRANSFORMER_PRIMARY_V = 230.0
DEFAULT_TRANSFORMER_SECONDARY_V = 6.0
DEFAULT_TRANSFORMER_PROBE_MULTIPLIER = 10.0


def capture_session(  # noqa: PLR0913 -- сборочная точка сессии: все параметры kw-only с дефолтами
    *,
    out_dir: Path,
    duration_s: float,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
    session_type: SessionType = SessionType.MEASUREMENT,
    ch1_range_v: float = DEFAULT_RANGE_V,
    label: str | None = None,
    series: SeriesPosition | None = None,
    scope_factory: Callable[[], ScopeProtocol] | None = None,
    ch1_setup: Ch1Setup | None = None,
    baseline_session: str | None = None,
    channel_mode: ChannelMode = ChannelMode.DUAL,
) -> Path:
    """Захватывает сессию и атомарно пишет её в ``out_dir``.

    ``ch1_range_v`` — номинал диапазона ВЧ-канала (5/1/0.5 В); CH2 всегда
    остаётся на +-5 В (трансформатор 230:6 даёт ~8.5 Vpk).

    ``channel_mode=CH1_ONLY`` — однокональный режим (один пробник):
    устройство стримит оба канала, но CH2 не сохраняется, а анализ
    идёт по номинальным окнам сети без фазовой привязки.
    """
    rate_code = _rate_code(sample_rate_hz)
    ch1_range_code = _range_code(ch1_range_v)
    normalized_label = validated_label(label)
    setup = _capture_setup(session_type=session_type, setup=ch1_setup)
    if session_type is SessionType.SELF_NOISE and baseline_session is not None:
        raise InputError("self-noise capture не принимает --baseline")
    if session_type is SessionType.LINE_QUALITY:
        if baseline_session is not None:
            raise InputError("line-quality capture не принимает --baseline")
        if channel_mode is not ChannelMode.CH1_ONLY:
            raise InputError("line-quality capture — одноканальный (--channels 1)")
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        raise InputError("длительность захвата должна быть положительной")
    requested_samples = round(duration_s * sample_rate_hz)
    parameters: dict[str, ParameterValue] = {"rate_code": rate_code}
    if normalized_label is not None:
        parameters["label"] = normalized_label
    if series is not None:
        parameters.update(series.as_parameters())
    factory = scope_factory if scope_factory is not None else open_real_scope
    created_utc = datetime.now(UTC).isoformat()
    scope = factory()
    ch1_raw, ch2_raw, telemetry = run_capture(
        scope,
        rate_code=rate_code,
        ch1_range_code=ch1_range_code,
        sample_rate_hz=sample_rate_hz,
        requested_samples=requested_samples,
    )
    id_suffix = series.id_suffix() if series is not None else ""
    manifest = SessionManifest(
        schema_version=CH1_MANIFEST_SCHEMA_VERSION,
        session_id=f"cap-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex}{id_suffix}",
        created_utc=created_utc,
        completed_utc=datetime.now(UTC).isoformat(),
        source=SessionSource.DEVICE,
        session_type=session_type,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
        sample_count=requested_samples,
        line_frequency_hz=LINE_FREQUENCY_HZ,
        profile=None,
        baseline_session=baseline_session,
        parameters=parameters,
        ch1=_ch1_meta(setup, range_code=ch1_range_code),
        ch2=(
            ChannelMeta(
                filename="ch2.npy",
                role=ChannelRole.LF_TRANSFORMER,
                unit="V",
                front_end=FRONT_END_CH2,
                range_code=RANGE_CODE_5V,
                probe_multiplier=1.0,
            )
            if channel_mode is ChannelMode.DUAL
            else None
        ),
        acquisition_telemetry=telemetry,
        synthetic_truth=None,
        ch1_setup=setup,
    )
    metadata = MetadataCollector().collect(
        settings=AcquisitionSettings(
            sample_rate_hz=sample_rate_hz,
            sample_count=requested_samples,
            probe_multiplier=_ch1_probe_multiplier(setup),
            range_v=ch1_range_v,
            channel_mode=channel_mode,
            front_end=_metadata_front_end(setup),
        ),
        telemetry=telemetry,
    )
    return write_session(
        session_dir=out_dir,
        manifest=manifest,
        ch1=_scale_raw(
            ch1_raw,
            range_code=ch1_range_code,
            probe_multiplier=_ch1_probe_multiplier(setup),
        ),
        ch2=(
            _scale_raw(ch2_raw, range_code=RANGE_CODE_5V)
            if channel_mode is ChannelMode.DUAL
            else None
        ),
        before_publish=lambda partial: write_initial_context(
            partial,
            manifest.session_id,
            metadata,
            label=normalized_label,
        ),
        after_publish=index_session,
    )


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
        case SessionType.MEASUREMENT:
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


def _rate_code(sample_rate_hz: float) -> int:
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("частота дискретизации должна быть конечной и положительной")
    megahertz = sample_rate_hz / MEGA
    if megahertz != round(megahertz) or not 1 <= round(megahertz) <= MAX_DUAL_RATE_MHZ:
        raise InputError(
            f"частота {sample_rate_hz:.0f} Гц: допустимы целые 1..{MAX_DUAL_RATE_MHZ} МГц (dual)",
        )
    return round(megahertz)


def _range_code(range_v: float) -> int:
    code = RANGE_CODES.get(range_v)
    if code is None:
        supported = "/".join(f"{value:g}" for value in RANGE_CODES)
        raise InputError(f"диапазон {range_v:g} В не поддерживается: допустимы {supported} В")
    return code


def _scale_raw(
    raw: NDArray[np.uint8],
    *,
    range_code: int,
    probe_multiplier: float = 1.0,
) -> Float32Array:
    scale = VOLTS_SCALE * probe_multiplier / float(range_code << 7)
    return ((raw.astype(np.float32) - ADC_CENTER) * scale).astype(np.float32)
