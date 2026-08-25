"""Неинвазивные маршруты устройства и capture preflight."""

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from lnt.capture_preflight import (
    BaselineCompatibility,
    CaptureEnvironment,
    CapturePreflightRequest,
    run_capture_preflight,
)
from lnt.types import (
    ChannelMode,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)
from lnt.ui.dependencies import AppServices, get_services
from lnt.ui.device import diagnose_device
from lnt.ui.models_capture import CapturePreflightBody

router = APIRouter(prefix="/api")
_Services = Annotated[AppServices, Depends(get_services)]


@router.get("/device/state")
def device_state() -> JSONResponse:
    """Возвращает T14 typed state без изменения устройства."""
    state = diagnose_device()
    return JSONResponse(
        {
            "state": state.state.value,
            "description_ru": state.description_ru,
            "recovery_action_ru": state.recovery_action_ru,
        }
    )


@router.post("/capture/preflight")
def capture_preflight(body: CapturePreflightBody, services: _Services) -> JSONResponse:
    """Возвращает T14 report до регистрации или запуска job."""
    status = diagnose_device()
    session_type = _session_type(body)
    setup = _setup(session_type)
    findings = run_capture_preflight(
        CapturePreflightRequest(
            session_root=services.root,
            session_type=session_type,
            channel_mode=ChannelMode.CH1_ONLY if body.channels == 1 else ChannelMode.DUAL,
            ch1_setup=setup,
            sample_rate_hz=body.sample_rate_hz,
            duration_s=body.duration_s,
            range_v=body.range_v,
            probe_multiplier=setup.probe_multiplier
            if isinstance(setup, TransformerLineProbe)
            else 1.0,
            baseline_requested=body.baseline_session is not None,
        ),
        CaptureEnvironment(
            device_state=status.state,
            free_bytes=shutil.disk_usage(_existing_parent(services.root)).free,
            root_writable=services.root.exists() and services.root.is_dir(),
            baseline_compatibility=(
                BaselineCompatibility.INCOMPATIBLE
                if body.baseline_session is not None
                else BaselineCompatibility.NOT_REQUESTED
            ),
            baseline_reason_code=(
                "baseline_requires_capture_resolution"
                if body.baseline_session is not None
                else None
            ),
        ),
    )
    return JSONResponse(
        {
            "ready": not any(item.severity.value == "block" for item in findings),
            "device_state": status.state.value,
            "findings": [{**asdict(item), "severity": item.severity.value} for item in findings],
        }
    )


def _session_type(body: CapturePreflightBody) -> SessionType:
    if body.input == "transformer":
        return SessionType.LINE_QUALITY
    if body.self_noise:
        return SessionType.SELF_NOISE
    return SessionType.MEASUREMENT


def _setup(
    session_type: SessionType,
) -> FloatingDifferentialRcShunt | ScopeInputTerminated | TransformerLineProbe:
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
            return ScopeInputTerminated(termination_resistance_ohm=50.0)
        case SessionType.LINE_QUALITY:
            return TransformerLineProbe(
                nominal_primary_v=230.0,
                nominal_secondary_v=6.0,
                probe_multiplier=10.0,
            )


def _existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        current = current.parent
    return current
