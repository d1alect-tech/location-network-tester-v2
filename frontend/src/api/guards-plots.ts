/** Runtime-guards полезных нагрузок графиков и деталей сессии (types-plots). */

import type {
  InputReferredSpectrumPayload,
  SessionDetailPayload,
  SpectrumPayload,
  WaveformPayload,
} from "./types-plots";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number");
}

/** Опциональный числовой ADD-ключ RBW-контракта: отсутствует, null или число. */
function isOptionalNumber(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "number";
}

/** Опциональный числовой массив (max-hold след B2): отсутствует или number[]. */
function isOptionalNumberArray(value: unknown): boolean {
  return value === undefined || isNumberArray(value);
}

export function isSpectrumPayload(value: unknown): value is SpectrumPayload {
  if (!isRecord(value)) return false;
  return (
    isNumberArray(value.frequency_hz) &&
    isNumberArray(value.psd_v2_per_hz) &&
    isOptionalNumberArray(value.psd_max_hold_v2_per_hz) &&
    typeof value.point_count === "number" &&
    isOptionalNumber(value.resolution_hz) &&
    isOptionalNumber(value.band_low_hz) &&
    isOptionalNumber(value.band_high_hz)
  );
}

export function isInputReferredSpectrumPayload(
  value: unknown,
): value is InputReferredSpectrumPayload {
  if (!isRecord(value)) return false;
  return (
    isNumberArray(value.frequency_hz) &&
    isNumberArray(value.input_referred_excess_psd_v2_per_hz) &&
    typeof value.point_count === "number" &&
    (value.status === null || value.status === undefined || typeof value.status === "string") &&
    (value.reason_code === null ||
      value.reason_code === undefined ||
      typeof value.reason_code === "string") &&
    typeof value.qualified_bin_count === "number" &&
    typeof value.total_bin_count === "number" &&
    isOptionalNumber(value.resolution_hz)
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
