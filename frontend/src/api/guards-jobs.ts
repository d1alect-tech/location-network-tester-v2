/** Runtime- guards полезных нагрузок задач панели (types-jobs). */

import { JOB_KINDS, JOB_STAGES, JOB_STATUSES } from "./types-jobs";
import type { JobListPayload, JobSnapshot } from "./types-jobs";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isIntOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isInteger(value));
}

/** Проверяет снимок задачи: канонический payload JobSnapshot.to_payload(). */
export function isJobSnapshot(value: unknown): value is JobSnapshot {
  if (!isRecord(value)) return false;
  return (
    typeof value.schema_version === "number" &&
    typeof value.version === "number" &&
    typeof value.job_id === "string" &&
    typeof value.kind === "string" &&
    (JOB_KINDS as readonly string[]).includes(value.kind) &&
    typeof value.status === "string" &&
    (JOB_STATUSES as readonly string[]).includes(value.status) &&
    typeof value.stage === "string" &&
    (JOB_STAGES as readonly string[]).includes(value.stage) &&
    isIntOrNull(value.series_index) &&
    isIntOrNull(value.series_total) &&
    isStringArray(value.written_sessions) &&
    (value.result === null || isRecord(value.result)) &&
    (value.error_code === null || typeof value.error_code === "string") &&
    (value.error_message === null || typeof value.error_message === "string")
  );
}

export function isJobListPayload(value: unknown): value is JobListPayload {
  return (
    isRecord(value) &&
    Array.isArray(value.items) &&
    value.items.every((item) => isJobSnapshot(item))
  );
}
