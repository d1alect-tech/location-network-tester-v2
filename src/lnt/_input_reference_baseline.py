"""Загрузка и compatibility-qualification явного CH1 self-noise baseline."""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from lnt.errors import InputError
from lnt.manifest import resolve_baseline_path
from lnt.session_store import LoadedSession, load_session
from lnt.spectrum import BandSpectrum, compute_band_spectrum
from lnt.types import AcquisitionTelemetry, ScopeInputTerminated, SessionManifest, SessionSource


@dataclass(frozen=True, slots=True, kw_only=True)
class CompatibleBaseline:
    """Явный self-noise baseline, совместимый с measurement Welch-grid."""

    session: LoadedSession
    spectrum: BandSpectrum


@dataclass(frozen=True, slots=True, kw_only=True)
class IncompatibleBaseline:
    """Machine-readable причина отсутствия безопасной baseline-коррекции."""

    reason_code: str


type BaselineResolution = CompatibleBaseline | IncompatibleBaseline


def resolve_compatible_baseline(
    *,
    session_dir: Path,
    measurement: LoadedSession,
    measurement_spectrum: BandSpectrum,
) -> BaselineResolution:
    """Возвращает baseline только при совпадении всех raw-Welch предпосылок."""
    baseline_path = resolve_baseline_path(session_dir, measurement.manifest)
    if baseline_path is None:
        return IncompatibleBaseline(reason_code="missing_explicit_baseline")
    try:
        baseline = load_session(baseline_path)
    except InputError:
        return IncompatibleBaseline(reason_code="baseline_unreadable")
    return _validate_loaded_baseline(measurement, measurement_spectrum, baseline)


def _validate_loaded_baseline(
    measurement: LoadedSession,
    measurement_spectrum: BandSpectrum,
    baseline: LoadedSession,
) -> BaselineResolution:
    """Проверяет загруженный baseline до его допуска к input-referral."""
    if (
        baseline.manifest.source is SessionSource.DEVICE
        and baseline.manifest.acquisition_telemetry is None
    ):
        return IncompatibleBaseline(reason_code="baseline_telemetry_missing")
    mismatch = _baseline_mismatch(measurement, baseline)
    if mismatch is not None:
        return IncompatibleBaseline(reason_code=mismatch)
    try:
        baseline_spectrum = compute_band_spectrum(
            baseline.ch1,
            sample_rate_hz=baseline.manifest.sample_rate_hz,
        )
    except InputError:
        return IncompatibleBaseline(reason_code="baseline_unreadable")
    if not _matching_grid(measurement_spectrum, baseline_spectrum):
        return IncompatibleBaseline(reason_code="baseline_frequency_grid_mismatch")
    return CompatibleBaseline(session=baseline, spectrum=baseline_spectrum)


def is_ch1_clipped(telemetry: AcquisitionTelemetry) -> bool:
    """Возвращает факт rail-clipping CH1 из явно присутствующей telemetry захвата."""
    return telemetry.ch1_clip_low_count + telemetry.ch1_clip_high_count > 0


def _baseline_mismatch(measurement: LoadedSession, baseline: LoadedSession) -> str | None:
    candidate = baseline.manifest
    expected = measurement.manifest
    telemetry = candidate.acquisition_telemetry
    checks = (
        (candidate.session_type.value != "self_noise", "baseline_session_type_mismatch"),
        (candidate.source != expected.source, "baseline_source_mismatch"),
        (candidate.sample_rate_hz != expected.sample_rate_hz, "baseline_sample_rate_mismatch"),
        (candidate.ch1.range_code != expected.ch1.range_code, "baseline_range_code_mismatch"),
        (candidate.ch1.unit != expected.ch1.unit, "baseline_unit_mismatch"),
        (
            candidate.ch1.probe_multiplier != expected.ch1.probe_multiplier,
            "baseline_probe_multiplier_mismatch",
        ),
        (
            _calibration_used(candidate) != _calibration_used(expected),
            "baseline_adc_calibration_mismatch",
        ),
        (not isinstance(candidate.ch1_setup, ScopeInputTerminated), "baseline_ch1_setup_mismatch"),
        (
            telemetry is not None and is_ch1_clipped(telemetry),
            "baseline_ch1_clipping",
        ),
    )
    return next((reason for mismatch, reason in checks if mismatch), None)


def _calibration_used(manifest: SessionManifest) -> bool:
    telemetry = manifest.acquisition_telemetry
    return telemetry.calibration_used if telemetry is not None else False


def _matching_grid(measurement: BandSpectrum, baseline: BandSpectrum) -> bool:
    return bool(
        math.isclose(measurement.resolution_hz, baseline.resolution_hz)
        and np.array_equal(measurement.frequencies_hz, baseline.frequencies_hz)
    )
