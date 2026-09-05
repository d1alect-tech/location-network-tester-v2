"""Сериализация фрагментов manifest.json (каналы, телеметрия, truth)."""

from lnt._manifest_json import JsonValue
from lnt.types import AcquisitionTelemetry, ChannelMeta, SyntheticTruth

__all__ = [
    "_serialize_channel",
    "_serialize_telemetry",
    "_serialize_truth",
]


def _serialize_channel(channel: ChannelMeta) -> dict[str, JsonValue]:
    return {
        "filename": channel.filename,
        "role": channel.role.value,
        "unit": channel.unit,
        "front_end": channel.front_end,
        "range_code": channel.range_code,
        "probe_multiplier": channel.probe_multiplier,
    }


def _serialize_telemetry(telemetry: AcquisitionTelemetry | None) -> dict[str, JsonValue] | None:
    if telemetry is None:
        return None
    return {
        "requested_samples": telemetry.requested_samples,
        "captured_samples": telemetry.captured_samples,
        "callback_count": telemetry.callback_count,
        "block_lengths": list(telemetry.block_lengths),
        "callback_gaps_s": list(telemetry.callback_gaps_s),
        "expected_block_interval_s": telemetry.expected_block_interval_s,
        "short_block_count": telemetry.short_block_count,
        "ch1_clip_low_count": telemetry.ch1_clip_low_count,
        "ch1_clip_high_count": telemetry.ch1_clip_high_count,
        "ch2_clip_low_count": telemetry.ch2_clip_low_count,
        "ch2_clip_high_count": telemetry.ch2_clip_high_count,
        "calibration_used": telemetry.calibration_used,
    }


def _serialize_truth(truth: SyntheticTruth | None) -> dict[str, JsonValue] | None:
    if truth is None:
        return None
    return {
        "needle_mean_v": truth.needle_mean_v,
        "needle_sigma_ratio": truth.needle_sigma_ratio,
        "needle_jitter_us": truth.needle_jitter_us,
        "ring_f0_hz": truth.ring_f0_hz,
        "ring_q": truth.ring_q,
        "async_rate_hz": truth.async_rate_hz,
        "lf_envelope_cv": truth.lf_envelope_cv,
    }
