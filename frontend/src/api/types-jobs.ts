/** Доменные типы задач панели: контракты src/lnt/ui/models.py и job_state.py.
 * Имена полей совпадают с JSON бэкенда (snake_case). */

export const JOB_KINDS = [
  "simulate",
  "capture",
  "analyze",
  "compare",
  "selftest",
  "device_check",
  "backup",
  "support_bundle",
] as const;
export type JobKind = (typeof JOB_KINDS)[number];

export const JOB_STATUSES = [
  "queued",
  "running",
  "cancelling",
  "succeeded",
  "cancelled",
  "failed",
  "interrupted",
] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export const JOB_STAGES = [
  "queued",
  "simulating",
  "capturing",
  "analyzing",
  "comparing",
  "selftest",
  "checking_device",
  "backup",
  "support_bundle",
  "done",
] as const;
export type JobStage = (typeof JOB_STAGES)[number];

/** Версионированный снимок задачи: JobSnapshot.to_payload(). */
export interface JobSnapshot {
  schema_version: number;
  version: number;
  job_id: string;
  kind: JobKind;
  status: JobStatus;
  stage: JobStage;
  series_index: number | null;
  series_total: number | null;
  written_sessions: string[];
  result: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
}

/** Общие поля серийных запросов (_SeriesRequest). */
interface SeriesFields {
  output_name?: string;
  label?: string;
  repeat?: number;
  interval_s?: number;
}

export type SimulateJobRequest = SeriesFields & {
  kind: "simulate";
  profile: string;
  duration_s?: number;
  sample_rate_hz?: number;
  seed?: number;
  channels?: 1 | 2;
};

export type CaptureJobRequest = SeriesFields & {
  kind: "capture";
  duration_s?: number;
  sample_rate_hz?: number;
  range_v?: number;
  self_noise?: boolean;
  baseline_session?: string | null;
  channels?: 1 | 2;
  input?: "rc" | "transformer";
};

export interface AnalyzeJobRequest {
  kind: "analyze";
  session_name: string;
}

export interface CompareJobRequest {
  kind: "compare";
  session_a: string;
  session_b: string;
}

export interface SelftestJobRequest {
  kind: "selftest";
}

export interface DeviceCheckJobRequest {
  kind: "device_check";
}

export interface BackupJobRequest {
  kind: "backup";
}

export interface SupportBundleJobRequest {
  kind: "support_bundle";
}

export type JobRequest =
  | SimulateJobRequest
  | CaptureJobRequest
  | AnalyzeJobRequest
  | CompareJobRequest
  | SelftestJobRequest
  | DeviceCheckJobRequest
  | BackupJobRequest
  | SupportBundleJobRequest;

/** Страница durable задач GET /api/jobs. */
export interface JobListPayload {
  items: JobSnapshot[];
}

/** Replay событий задачи GET /api/jobs/{id}/history. */
export interface JobHistoryPayload {
  items: JobSnapshot[];
}
