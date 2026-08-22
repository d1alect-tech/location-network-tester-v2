/** Runtime-guards артефактов анализа v2 (types-analysis). Битый JSON
 * событий или некорректные числа отклоняются до попадания в состояние UI. */

import type { CandidateEventPayload, EventInventoryPayload } from "./types-analysis";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Строгая проверка события: все числовые поля конечны, флаги — boolean. */
export function isCandidateEvent(value: unknown): value is CandidateEventPayload {
  return (
    isRecord(value) &&
    [
      "start_sample",
      "end_sample",
      "peak_sample",
      "start_time_s",
      "end_time_s",
      "peak_time_s",
      "peak_value_v",
      "excess_energy_v2_s",
      "snr",
    ].every((field) => isFiniteNumber(value[field])) &&
    typeof value.polarity === "string" &&
    (value.dominant_band === null || typeof value.dominant_band === "string") &&
    typeof value.qualification_status === "string" &&
    typeof value.boundary === "boolean" &&
    typeof value.clipped === "boolean"
  );
}

/** Проверяет ответ events.json: версия схемы, счётчик и массив событий. */
export function isEventInventoryPayload(value: unknown): value is EventInventoryPayload {
  return (
    isRecord(value) &&
    isFiniteNumber(value.schema_version) &&
    isFiniteNumber(value.sample_count) &&
    Array.isArray(value.events) &&
    value.events.every((event) => isCandidateEvent(event))
  );
}
