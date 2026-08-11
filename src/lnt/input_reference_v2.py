"""Recipe-artifact correction of qualified CH1 excess PSD."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, override

import numpy as np
from numpy.typing import NDArray

from lnt._input_reference_v2_artifact import CorrectedInputReference
from lnt.context.json_codec import JsonValue, encode_canonical
from lnt.input_reference import QUALIFICATION_RULE_ID, correction_for_frequencies
from lnt.spectrum import find_qualified_peaks
from lnt.uncertainty import standard_uncertainty

if TYPE_CHECKING:
    from lnt.types import FloatingDifferentialRcShunt
    from lnt.uncertainty.models import TypeBDistribution

Float64Array = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
MODEL_VERSION: Final = "floating_differential_rc_shunt_v1"
TRANSFER_FORMULA: Final = "|H(f)|^2=x^2/(1+x^2), x=2*pi*f*R*C_eq"
MANIFEST_SCHEMA_VERSION: Final = 2


@dataclass(frozen=True, slots=True)
class CorrectionError(Exception):
    """Типизированный отказ до создания corrected artifact."""

    reason_code: str

    @override
    def __str__(self) -> str:
        """Возвращает русское диагностическое сообщение с reason code."""
        return f"input-reference correction недоступна: {self.reason_code}"


class GridMismatchError(CorrectionError):
    """Baseline и measurement не имеют идентичной Welch-сетки."""


class IdentityMismatchError(CorrectionError):
    """Заявленный identity hash не соответствует каноническим данным."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasurementPsd:
    """Предварительно проверенная scope-plane PSD measurement."""

    frequencies_hz: Float64Array
    psd_v2_per_hz: Float64Array
    resolution_hz: float
    identity_sha256: str

    @classmethod
    def create(
        cls,
        *,
        frequencies_hz: Float64Array,
        psd_v2_per_hz: Float64Array,
        resolution_hz: float,
    ) -> MeasurementPsd:
        """Проверяет PSD boundary и вычисляет канонический SHA-256 identity."""
        _validate_plane(frequencies_hz, psd_v2_per_hz, resolution_hz)
        return cls(
            frequencies_hz=frequencies_hz.copy(),
            psd_v2_per_hz=psd_v2_per_hz.copy(),
            resolution_hz=resolution_hz,
            identity_sha256=_plane_hash(frequencies_hz, psd_v2_per_hz, resolution_hz),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BaselinePsd:
    """Предварительно проверенная совместимая scope-plane baseline PSD."""

    frequencies_hz: Float64Array
    psd_v2_per_hz: Float64Array
    resolution_hz: float
    identity_sha256: str

    @classmethod
    def create(
        cls,
        *,
        frequencies_hz: Float64Array,
        psd_v2_per_hz: Float64Array,
        resolution_hz: float,
    ) -> BaselinePsd:
        """Проверяет PSD boundary и вычисляет канонический SHA-256 identity."""
        _validate_plane(frequencies_hz, psd_v2_per_hz, resolution_hz)
        return cls(
            frequencies_hz=frequencies_hz.copy(),
            psd_v2_per_hz=psd_v2_per_hz.copy(),
            resolution_hz=resolution_hz,
            identity_sha256=_plane_hash(frequencies_hz, psd_v2_per_hz, resolution_hz),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RcUncertaintyProfile:
    """Явные Type-B распределения R/C; независимость не предполагается."""

    resistance: TypeBDistribution
    c1: TypeBDistribution
    c2: TypeBDistribution
    independent_components: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectionRequest:
    """Все объявленные входы одного recipe correction artifact."""

    measurement: MeasurementPsd
    baseline: BaselinePsd
    model: FloatingDifferentialRcShunt | None
    uncertainty: RcUncertaintyProfile | None = None
    manifest_schema_version: int = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class UnavailableCorrection:
    """Reason-coded отказ, не отменяющий валидность raw scope-plane PSD."""

    reason_code: str
    raw_scope_plane_valid: bool = True


type CorrectionOutcome = CorrectedInputReference | UnavailableCorrection


def correct_input_reference(request: CorrectionRequest) -> CorrectionOutcome:
    """Корректирует только ≥2× excess PSD без интерполяции failed bins."""
    if request.manifest_schema_version != MANIFEST_SCHEMA_VERSION:
        return UnavailableCorrection(reason_code="manifest_schema_v1")
    if request.model is None:
        return UnavailableCorrection(reason_code="measurement_ch1_setup_missing")
    _verify_identities(request)
    _require_matching_grid(request.measurement, request.baseline)
    model = request.model
    measurement = request.measurement
    baseline = request.baseline
    qualified = measurement.psd_v2_per_hz >= 2.0 * baseline.psd_v2_per_hz
    excess = measurement.psd_v2_per_hz - baseline.psd_v2_per_hz
    gains = correction_for_frequencies(model, measurement.frequencies_hz)
    corrected = np.full_like(excess, np.nan)
    corrected[qualified] = excess[qualified] / gains[qualified] ** 2
    asd = np.sqrt(corrected)
    uncertainty, reason = _propagate_uncertainty(request, excess, qualified)
    power = float(np.sum(corrected[qualified]) * measurement.resolution_hz)
    equivalent = (model.c1_f * model.c2_f) / (model.c1_f + model.c2_f)
    metadata: dict[str, JsonValue] = {
        "model_version": MODEL_VERSION,
        "transfer_formula": TRANSFER_FORMULA,
        "resistance_ohm": model.resistance_ohm,
        "c1_f": model.c1_f,
        "c2_f": model.c2_f,
        "c_eq_f": equivalent,
        "f_3db_hz": 1.0 / (2.0 * math.pi * model.resistance_ohm * equivalent),
        "component_values_basis": model.component_values_basis.value,
        "reference_assumption": model.reference_assumption.value,
        "qualification_rule_id": QUALIFICATION_RULE_ID,
        "measurement_identity_sha256": measurement.identity_sha256,
        "baseline_identity_sha256": baseline.identity_sha256,
    }
    return CorrectedInputReference(
        frequencies_hz=measurement.frequencies_hz.copy(),
        corrected_psd_v2_per_hz=corrected,
        corrected_asd_v_per_sqrt_hz=asd,
        corrected_standard_uncertainty_v2_per_hz=uncertainty,
        uncertainty_reason_code=reason,
        qualified=qualified,
        corrected_peaks=find_qualified_peaks(measurement.frequencies_hz, corrected, qualified),
        qualified_band_power_v2=power,
        qualified_band_rms_v=math.sqrt(power),
        metadata=metadata,
    )


def _propagate_uncertainty(
    request: CorrectionRequest,
    excess: Float64Array,
    qualified: BoolArray,
) -> tuple[Float64Array | None, str | None]:
    """Линеаризует y=excess/|H|² в номинальной точке R/C1/C2."""
    profile = request.uncertainty
    model = request.model
    if profile is None or model is None:
        return None, "missing_type_b_component"
    if not profile.independent_components:
        return None, "independence_not_declared"
    c_sum = model.c1_f + model.c2_f
    c_eq = model.c1_f * model.c2_f / c_sum
    x = 2.0 * np.pi * request.measurement.frequencies_hz * model.resistance_ohm * c_eq
    common = -2.0 * excess / x**2
    sensitivities = (
        common / model.resistance_ohm,
        common / c_eq * model.c2_f**2 / c_sum**2,
        common / c_eq * model.c1_f**2 / c_sum**2,
    )
    sigmas = tuple(
        standard_uncertainty(item)[1] for item in (profile.resistance, profile.c1, profile.c2)
    )
    combined = np.sqrt(
        sum(
            (sensitivity * sigma) ** 2
            for sensitivity, sigma in zip(sensitivities, sigmas, strict=True)
        )
    )
    result = np.full_like(excess, np.nan)
    result[qualified] = combined[qualified]
    return result, None


def _validate_plane(frequencies: Float64Array, psd: Float64Array, resolution: float) -> None:
    if frequencies.ndim != 1 or frequencies.shape != psd.shape or frequencies.size == 0:
        raise CorrectionError("invalid_psd_shape")
    if not np.all(np.isfinite(frequencies)) or not np.all(np.isfinite(psd)):
        raise CorrectionError("nonfinite_psd_input")
    if np.any(frequencies <= 0.0) or np.any(np.diff(frequencies) <= 0.0) or np.any(psd < 0.0):
        raise CorrectionError("invalid_psd_values")
    if not math.isfinite(resolution) or resolution <= 0.0:
        raise CorrectionError("invalid_frequency_resolution")


def _plane_hash(frequencies: Float64Array, psd: Float64Array, resolution: float) -> str:
    payload: dict[str, JsonValue] = {
        "frequencies_hz": frequencies.tolist(),
        "psd_v2_per_hz": psd.tolist(),
        "resolution_hz": resolution,
    }
    return hashlib.sha256(encode_canonical(payload, "input-reference PSD identity")).hexdigest()


def _verify_identities(request: CorrectionRequest) -> None:
    measurement = request.measurement
    baseline = request.baseline
    if measurement.identity_sha256 != _plane_hash(
        measurement.frequencies_hz,
        measurement.psd_v2_per_hz,
        measurement.resolution_hz,
    ):
        raise IdentityMismatchError("measurement_identity_hash_mismatch")
    if baseline.identity_sha256 != _plane_hash(
        baseline.frequencies_hz,
        baseline.psd_v2_per_hz,
        baseline.resolution_hz,
    ):
        raise IdentityMismatchError("baseline_identity_hash_mismatch")


def _require_matching_grid(measurement: MeasurementPsd, baseline: BaselinePsd) -> None:
    if measurement.resolution_hz != baseline.resolution_hz or not np.array_equal(
        measurement.frequencies_hz,
        baseline.frequencies_hz,
    ):
        raise GridMismatchError("baseline_frequency_grid_mismatch")
