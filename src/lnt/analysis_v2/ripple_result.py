"""Нормализованные блоки payload ``ripple.json`` v1: идентичности и QC.

Измерительные блоки (тайм-домен, интервалы, спектр, полосы) вынесены в
``ripple_measurements``; здесь остаются идентичности сессии/алгоритма,
провенанс, адаптер, выбор исходного спана и QC-ценз.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.types import SessionSource

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.ripple.adapter import AdapterSpec
    from lnt.types import SessionManifest

    from .ripple_qc import SpanQc

ALGORITHM_ID: Final = "ripple_observed_v1"
ALGORITHM_VERSION: Final = 1
RMS_ACCUMULATION: Final = "population_centered_float64"
CAPTURE_METADATA_BASIS: Final = "legacy_capture_metadata_not_adapter_provenance"
CALIBRATION_IDENTITY_LEGACY: Final = "legacy_bit_identical_conversion"
NONFINITE_COUNT_SCOPE: Final = "selected_span"


def algorithm_block() -> dict[str, object]:
    """Идентичность алгоритма воспроизводимости."""
    return {"id": ALGORITHM_ID, "version": ALGORITHM_VERSION, "rms": RMS_ACCUMULATION}


def options_block(
    *, band_low_hz: float, band_high_hz: float, interval_window_s: float
) -> dict[str, object]:
    """Запрошенные опции оценки: полоса и окно интервалов."""
    return {
        "band_low_hz": float(band_low_hz),
        "band_high_hz": float(band_high_hz),
        "interval_window_s": float(interval_window_s),
    }


def session_block(
    *,
    manifest: SessionManifest,
    hashes: Mapping[str, str],
) -> dict[str, object]:
    """Идентичность сессии с хэшами входов."""
    return {
        "session_id": manifest.session_id,
        "manifest_sha256": hashes["manifest_sha256"],
        "ch1_sha256": hashes["ch1_sha256"],
        "channel": "ch1",
        "source": manifest.source.value,
    }


def provenance_block(
    *,
    manifest: SessionManifest,
    settling: str,
) -> dict[str, object]:
    """Провенанс захвата против объявленного оператором подключения."""
    telemetry = manifest.acquisition_telemetry
    calibration_used: bool | None = telemetry.calibration_used if telemetry else None
    if manifest.source is SessionSource.SYNTHETIC:
        voltage_plane = "synthetic_mathematical_volts"
    elif calibration_used is False:
        voltage_plane = "recorded_ch1_volts_observed_uncalibrated"
    else:
        voltage_plane = "recorded_ch1_volts_observed_calibration_identity_unknown"
    return {
        "capture_metadata_basis": CAPTURE_METADATA_BASIS,
        "operator_attachment": settling,
        "voltage_plane": voltage_plane,
        "range_code": int(manifest.ch1.range_code),
        "probe_multiplier": float(manifest.ch1.probe_multiplier),
        "calibration_used": calibration_used,
        "calibration_identity": (
            CALIBRATION_IDENTITY_LEGACY if calibration_used is False else None
        ),
        "hardware_qualification": "unverified",
    }


def adapter_block(adapter: AdapterSpec) -> dict[str, object]:
    """Номинальная модель адаптера с честными ограничениями."""
    return {
        "topology_id": adapter.topology_id,
        "cap_nf": float(adapter.cap_nf),
        "series_r_ohm": float(adapter.series_r_ohm),
        "rin_ohm": float(adapter.rin_ohm),
        "probe_multiplier": int(adapter.probe_multiplier),
        "component_values_basis": adapter.component_values_basis.value,
        "rail_nominal_v": (
            float(adapter.rail_nominal_v) if adapter.rail_nominal_v is not None else None
        ),
        "fc_hz": float(adapter.fc_hz) if adapter.fc_hz is not None else None,
        "tau_s": float(adapter.tau_s) if adapter.tau_s is not None else None,
        "plateau_gain": float(adapter.plateau_gain) if adapter.plateau_gain is not None else None,
        "transfer_status": adapter.transfer_status.value,
        "assumption_codes": list(adapter.assumption_codes),
    }


def selection_block(*, qc: SpanQc, sample_rate_hz: float) -> dict[str, object]:
    """Исходные границы выбранного спана и база исключённого префикса."""
    span_count = qc.span_count
    return {
        "sample_start_index": int(qc.sample_start_index),
        "sample_end_index_exclusive": int(qc.sample_end_index_exclusive),
        "sample_count": int(span_count),
        "sample_rate_hz": float(sample_rate_hz),
        "realized_duration_s": float(span_count / sample_rate_hz),
        "excluded_prefix_samples": int(qc.excluded_prefix_samples),
        "settling_prefix_samples_nominal": int(qc.settling_prefix_samples_nominal),
        "settling_basis": qc.settling_basis,
        "continuity_status": qc.continuity_status,
        "continuity_reason_codes": list(qc.continuity_reason_codes),
    }


def qc_block(qc: SpanQc) -> dict[str, object]:
    """Ценз клиппинга/не-конечности и коды причин выбранного спана."""
    return {
        "clipping_assessment": qc.clipping_assessment,
        "clip_count_scope": qc.clip_count_scope,
        "clip_low_count": qc.clip_low_count,
        "clip_high_count": qc.clip_high_count,
        "nonfinite_count": int(qc.nonfinite_count),
        "nonfinite_count_scope": NONFINITE_COUNT_SCOPE,
        "record_nonfinite_count": int(qc.record_nonfinite_count),
        "dropped_samples": qc.dropped_samples,
        "reason_codes": list(qc.span_reason_codes),
    }
