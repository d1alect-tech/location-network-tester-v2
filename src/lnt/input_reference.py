"""Модельное input-referred excess-PSD CH1 после raw Welch без deconvolution иголок."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt._input_reference_baseline import (
    CompatibleBaseline,
    IncompatibleBaseline,
    is_ch1_clipped,
    resolve_compatible_baseline,
)
from lnt._manifest_ch1_setup import FLOATING_KIND, model_kind
from lnt.session_store import LoadedSession
from lnt.spectrum import BandSpectrum, SpectrumPeak, find_qualified_peaks
from lnt.swept_response import SweptResponse, swept_gain_at
from lnt.types import (
    CH1_MANIFEST_SCHEMA_VERSION,
    FloatingDifferentialRcShunt,
    SessionSource,
    SessionType,
)

Float64Array = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
QUALIFICATION_RULE_ID: Final = "measurement_psd_gte_2x_baseline_psd_v1"


class InputReferenceStatus(StrEnum):
    """Статус input-reference по явному machine-readable контракту."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True, kw_only=True)
class InputReferenceModel:
    """Machine-readable provenance floating RC transfer-model input referral."""

    kind: str
    resistance_ohm: float
    c1_f: float
    c2_f: float
    component_values_basis: str
    reference_assumption: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Ch1InputReference:
    """Результат квалификации baseline и, если возможно, excess PSD."""

    status: InputReferenceStatus
    reason_code: str | None
    model_kind: str | None
    input_referred_excess_psd_v2_per_hz: Float64Array | None
    qualified: BoolArray | None
    baseline_session_id: str | None
    model: InputReferenceModel | None
    qualification_rule_id: str | None
    qualified_bin_count: int
    total_bin_count: int
    corrected_peaks: tuple[SpectrumPeak, ...]


def correction_for_frequencies(
    model: FloatingDifferentialRcShunt,
    frequencies_hz: Float64Array,
    *,
    swept: SweptResponse | None = None,
) -> Float64Array:
    """Возвращает |H|: измеренный swept поверх номинала; без swept — номинал."""
    if swept is not None:
        return swept_gain_at(swept, frequencies_hz)
    equivalent_capacitance_f = _equivalent_capacitance(model)
    angular = 2.0 * np.pi * frequencies_hz
    numerator = angular * model.resistance_ohm * equivalent_capacitance_f
    return numerator / np.sqrt(1.0 + numerator**2)


def derive_input_reference(
    session_dir: Path,
    measurement: LoadedSession,
    measurement_spectrum: BandSpectrum,
    *,
    swept: SweptResponse | None = None,
) -> Ch1InputReference:
    """Квалифицирует baseline и выводит только явный excess PSD на входе схемы."""
    setup = measurement.manifest.ch1_setup
    kind = model_kind(setup)
    measurement_reason = _measurement_unavailable_reason(measurement)
    if measurement_reason is not None:
        return _unavailable(measurement_reason, kind)
    if not isinstance(setup, FloatingDifferentialRcShunt):
        return _unavailable("measurement_ch1_setup_mismatch", kind)
    baseline = resolve_compatible_baseline(
        session_dir=session_dir,
        measurement=measurement,
        measurement_spectrum=measurement_spectrum,
    )
    match baseline:
        case IncompatibleBaseline(reason_code=reason_code):
            return _unavailable(reason_code, kind)
        case CompatibleBaseline(session=baseline_session, spectrum=baseline_spectrum):
            return _derive_qualified_reference(
                measurement_spectrum=measurement_spectrum,
                baseline_spectrum=baseline_spectrum,
                setup=setup,
                baseline_session_id=baseline_session.manifest.session_id,
                swept=swept,
            )


def _derive_qualified_reference(
    *,
    measurement_spectrum: BandSpectrum,
    baseline_spectrum: BandSpectrum,
    setup: FloatingDifferentialRcShunt,
    baseline_session_id: str,
    swept: SweptResponse | None = None,
) -> Ch1InputReference:
    """Применяет excess PSD referral только к уже совместимому baseline."""
    qualified = measurement_spectrum.psd_v2_per_hz >= 2.0 * baseline_spectrum.psd_v2_per_hz
    excess = measurement_spectrum.psd_v2_per_hz - baseline_spectrum.psd_v2_per_hz
    gains = correction_for_frequencies(setup, measurement_spectrum.frequencies_hz, swept=swept)
    input_excess = np.full_like(excess, np.nan)
    input_excess[qualified] = excess[qualified] / gains[qualified] ** 2
    return Ch1InputReference(
        status=InputReferenceStatus.AVAILABLE,
        reason_code=None,
        model_kind=FLOATING_KIND,
        input_referred_excess_psd_v2_per_hz=input_excess,
        qualified=qualified,
        baseline_session_id=baseline_session_id,
        model=_input_reference_model(setup),
        qualification_rule_id=QUALIFICATION_RULE_ID,
        qualified_bin_count=int(np.count_nonzero(qualified)),
        total_bin_count=int(qualified.size),
        corrected_peaks=find_qualified_peaks(
            measurement_spectrum.frequencies_hz,
            input_excess,
            qualified,
        ),
    )


def _equivalent_capacitance(model: FloatingDifferentialRcShunt) -> float:
    return (model.c1_f * model.c2_f) / (model.c1_f + model.c2_f)


def _input_reference_model(model: FloatingDifferentialRcShunt) -> InputReferenceModel:
    return InputReferenceModel(
        kind=FLOATING_KIND,
        resistance_ohm=model.resistance_ohm,
        c1_f=model.c1_f,
        c2_f=model.c2_f,
        component_values_basis=model.component_values_basis.value,
        reference_assumption=model.reference_assumption.value,
    )


def _unavailable(reason_code: str, kind: str | None) -> Ch1InputReference:
    return Ch1InputReference(
        status=InputReferenceStatus.UNAVAILABLE,
        reason_code=reason_code,
        model_kind=kind,
        input_referred_excess_psd_v2_per_hz=None,
        qualified=None,
        baseline_session_id=None,
        model=None,
        qualification_rule_id=None,
        qualified_bin_count=0,
        total_bin_count=0,
        corrected_peaks=(),
    )


def _measurement_unavailable_reason(measurement: LoadedSession) -> str | None:
    manifest = measurement.manifest
    setup = manifest.ch1_setup
    if manifest.schema_version != CH1_MANIFEST_SCHEMA_VERSION:
        return "manifest_schema_v1"
    match manifest.session_type:
        case SessionType.MEASUREMENT:
            pass
        case (
            SessionType.SELF_NOISE
            | SessionType.LINE_QUALITY
            | SessionType.CM_DM
            | SessionType.CM_DM_CALIBRATION
        ):
            return "measurement_session_type_mismatch"
    if not isinstance(setup, FloatingDifferentialRcShunt):
        return "measurement_ch1_setup_mismatch"
    match manifest.source:
        case SessionSource.DEVICE:
            if manifest.acquisition_telemetry is None:
                return "measurement_telemetry_missing"
        case SessionSource.SYNTHETIC:
            pass
    telemetry = manifest.acquisition_telemetry
    return (
        "measurement_ch1_clipping" if telemetry is not None and is_ch1_clipped(telemetry) else None
    )
