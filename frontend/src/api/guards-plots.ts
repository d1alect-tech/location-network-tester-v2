/** Runtime-guards полезных нагрузок графиков и деталей сессии (types-plots). */

import type { SessionDetailPayload, SpectrumPayload, WaveformPayload } from "./types-plots";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number");
}

export function isSpectrumPayload(value: unknown): value is SpectrumPayload {
  if (!isRecord(value)) return false;
  return (
    isNumberArray(value.frequency_hz) &&
    isNumberArray(value.psd_v2_per_hz) &&
    typeof value.point_count === "number"
  );
}

export function isWaveformPayload(value: unknown): value is WaveformPayload {
  if (!isRecord(value)) return false;
  return (
    (value.channel === "ch1" || value.channel === "ch2") &&
    isNumberArray(value.time_s) &&
    isNumberArray(value.voltage_v) &&
    typeof value.point_count === "number"
  );
}

/** Манифест/анализ — открытые JSON-объекты бэкенда; проверяем только конверт. */
export function isSessionDetailPayload(value: unknown): value is SessionDetailPayload {
  if (!isRecord(value)) return false;
  return (
    typeof value.name === "string" &&
    isRecord(value.manifest) &&
    (value.analysis === null || isRecord(value.analysis)) &&
    typeof value.spectrum_available === "boolean" &&
    typeof value.waveform_available === "boolean" &&
    typeof value.ch2_available === "boolean"
  );
}
