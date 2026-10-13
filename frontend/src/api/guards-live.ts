/** Runtime-guards живого контракта (types-live, источник models_live.py).
 * Сужение до доступа: сырой JSON не доверяется, некорректный кадр
 * игнорируется без остановки потока. */

import type { LiveFramePayload, LiveStatePayload, LiveTrigger } from "./types-live";

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
