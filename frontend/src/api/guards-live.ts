/** Runtime-guards живого контракта (types-live, источник models_live.py).
 * Сужение до доступа: сырой JSON не доверяется, некорректный кадр
 * игнорируется без остановки потока. */

import type {
  LiveFramePayload,
  LiveRippleAdapterPayload,
  LiveRipplePayload,
  LiveSaConfig,
  LiveSpectrumPayload,
  LiveStatePayload,
  LiveTrigger,
} from "./types-live";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number");
}

export function isLiveTrigger(value: unknown): value is LiveTrigger {
  if (!isRecord(value)) return false;
  return (
    typeof value.level_v === "number" &&
    (value.slope === "rising" || value.slope === "falling") &&
    (value.source === "ch1" || value.source === "ch2") &&
    (value.mode === "auto" || value.mode === "normal" || value.mode === "single") &&
    typeof value.auto_timeout_s === "number"
  );
}

export function isLiveStatePayload(value: unknown): value is LiveStatePayload {
  if (!isRecord(value)) return false;
  return (
    (value.state === "idle" || value.state === "running" || value.state === "stopped") &&
    (value.mode === "real" || value.mode === "sim") &&
    (value.busy_reason === null || typeof value.busy_reason === "string") &&
    (value.trigger === null || isLiveTrigger(value.trigger))
  );
}

const SA_WINDOWS = ["hann", "flattop", "kaiser", "blackman", "rect"] as const;
const SA_DETECTORS = ["mean", "rms", "max-hold", "min-hold"] as const;

/** SA-конфигурация: селекторы и полоса; Найквист проверяет бэкенд. */
export function isLiveSaConfig(value: unknown): value is LiveSaConfig {
  if (!isRecord(value)) return false;
  return (
    typeof value.rbw_hz === "number" &&
    typeof value.band_low_hz === "number" &&
    typeof value.band_high_hz === "number" &&
    SA_WINDOWS.includes(value.window as (typeof SA_WINDOWS)[number]) &&
    SA_DETECTORS.includes(value.detector as (typeof SA_DETECTORS)[number])
  );
}

export function isLiveSpectrumPayload(value: unknown): value is LiveSpectrumPayload {
  if (!isRecord(value)) return false;
  if (!isNumberArray(value.freq) || !isNumberArray(value.psd_db)) return false;
  if (value.freq.length !== value.psd_db.length || value.freq.length === 0) return false;
  if (!Array.isArray(value.peaks) || !value.peaks.every(isLiveSaPeak)) return false;
  const meta = value.meta;
  if (!isRecord(meta)) return false;
  return (
    typeof value.frame_index === "number" &&
    typeof meta.enbw === "number" &&
    typeof meta.resolution === "number" &&
    typeof meta.rbw === "number" &&
    typeof meta.window === "string"
  );
}

function isLiveSaPeak(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    typeof value.frequency_hz === "number" &&
    typeof value.level_db === "number" &&
    typeof value.prominence_db === "number" &&
    (value.q_factor === null || typeof value.q_factor === "number")
  );
}

function isLiveChannelSeries(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    isNumberArray(value.time_s) &&
    isNumberArray(value.voltage_v) &&
    typeof value.point_count === "number"
  );
}

export function isLiveFramePayload(value: unknown): value is LiveFramePayload {
  if (!isRecord(value)) return false;
  return (
    typeof value.frame_index === "number" &&
    typeof value.triggered === "boolean" &&
    typeof value.emitted_at_s === "number" &&
    typeof value.dropped_samples === "number" &&
    typeof value.skipped_frames === "number" &&
    typeof value.sample_rate_hz === "number" &&
    typeof value.frame_samples === "number" &&
    typeof value.decimated === "boolean" &&
    typeof value.calibration_used === "boolean" &&
    isLiveChannelSeries(value.ch1) &&
    isLiveChannelSeries(value.ch2)
  );
}

const RIPPLE_STATUSES = ["settling", "unavailable", "ready", "stopped"] as const;
const RIPPLE_CONTINUITY = ["host_contiguous_unverified", "synthetic_exact"] as const;
const RIPPLE_SETTLING = ["capture_start_assuming_preconnected", "settling_unknown"] as const;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isFiniteOrNull(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}

function isCountOrNull(value: unknown): value is number | null {
  return value === null || isCount(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isLiveRippleAdapter(value: unknown): value is LiveRippleAdapterPayload {
  if (!isRecord(value)) return false;
  return (
    typeof value.topology_id === "string" &&
    isFiniteNumber(value.cap_nf) &&
    isFiniteNumber(value.series_r_ohm) &&
    isFiniteNumber(value.probe_multiplier) &&
    typeof value.component_values_basis === "string" &&
    typeof value.hardware_qualification === "string" &&
    typeof value.transfer_status === "string" &&
    isFiniteOrNull(value.rail_nominal_v) &&
    isFiniteOrNull(value.tau_s) &&
    isFiniteOrNull(value.fc_hz) &&
    isFiniteOrNull(value.settling_s) &&
    isCountOrNull(value.settle_samples) &&
    isStringArray(value.assumption_codes)
  );
}

/** Событие ripple (models_ripple_live.py): строгая ЖИВАЯ схема — конечные
 * числа, неотрицательные целые счётчики и инвариант статуса «числа ровно у
 * ready». Битое событие отбрасывается — чип гасится, поток живёт. */
export function isLiveRipplePayload(value: unknown): value is LiveRipplePayload {
  if (!isRecord(value)) return false;
  if (!RIPPLE_STATUSES.includes(value.status as (typeof RIPPLE_STATUSES)[number])) return false;
  if (!RIPPLE_CONTINUITY.includes(value.continuity_basis as (typeof RIPPLE_CONTINUITY)[number]))
    return false;
  if (!RIPPLE_SETTLING.includes(value.settling_basis as (typeof RIPPLE_SETTLING)[number]))
    return false;
  if (!isStringArray(value.reason_codes)) return false;
  if (!isCount(value.epoch_id) || !isCount(value.continuity_id)) return false;
  if (!isCount(value.gap_count) || !isCount(value.block_count)) return false;
  if (!isCount(value.dropped_blocks) || !isCount(value.dropped_samples)) return false;
  if (!isCount(value.samples_received) || !isCount(value.sample_progress)) return false;
  if (!isCount(value.ring_capacity_samples) || !isCount(value.ring_sample_count)) return false;
  if (!isCount(value.startup_discard_samples)) return false;
  if (!isCountOrNull(value.settle_samples)) return false;
  if (!isCount(value.span_sample_count)) return false;
  if (!isCount(value.clipped_low) || !isCount(value.clipped_high)) return false;
  if (!isCountOrNull(value.settling_remaining_samples)) return false;
  if (!isCountOrNull(value.excluded_prefix_samples)) return false;
  if (!isCountOrNull(value.span_start_sample)) return false;
  if (typeof value.config_id !== "string") return false;
  if (typeof value.settled !== "boolean" || typeof value.ring_limited !== "boolean") return false;
  if (typeof value.calibration_used !== "boolean") return false;
  if (!isFiniteOrNull(value.span_duration_s)) return false;
  if (!isFiniteOrNull(value.mean_v) || !isFiniteOrNull(value.rms_ac_v)) return false;
  if (!isFiniteOrNull(value.vpp_v)) return false;
  // sample_rate_hz — делитель прогресса установления: конечна и > 0.
  if (!isFiniteNumber(value.sample_rate_hz) || value.sample_rate_hz <= 0) return false;
  if (!isFiniteNumber(value.ch1_range_v) || value.ch1_range_v <= 0) return false;
  if (!isFiniteNumber(value.ch1_probe_multiplier) || value.ch1_probe_multiplier <= 0) return false;
  if (value.clip_count_scope !== "current_span") return false;
  if (value.voltage_label !== "некалиброванные вольты") return false;
  // Инвариант статуса: числа ровно у ready, иначе все три null.
  const metrics = [value.mean_v, value.rms_ac_v, value.vpp_v];
  if (value.status === "ready" && metrics.some((metric) => metric === null)) return false;
  if (value.status !== "ready" && metrics.some((metric) => metric !== null)) return false;
  return isLiveRippleAdapter(value.adapter);
}
