/** Доменные под-клиенты задач панели (Todos 14–18) и графиков (Todo 27).
 * Все мутации подписываются nonce запуска через requestJson(mutation:true);
 * ответы проверяются runtime-guards перед выдачей типизированного значения. */

import type { LntApiClient, RequestOptions } from "./client";
import { ApiError } from "./errors";
import { isJobListPayload, isJobSnapshot } from "./guards-jobs";
import { isSessionDetailPayload, isSpectrumPayload, isWaveformPayload } from "./guards-plots";
import type { JobHistoryPayload, JobListPayload, JobRequest, JobSnapshot } from "./types-jobs";
import type {
  SessionDetailPayload,
  SpectrumPayload,
  WaveformChannel,
  WaveformPayload,
} from "./types-plots";

async function snapshotFrom(pending: Promise<unknown>): Promise<JobSnapshot> {
  const payload = await pending;
  if (!isJobSnapshot(payload)) throw new ApiError("parse");
  return payload;
}

export interface JobsApi {
  /** POST /api/jobs → 202 с первым снимком задачи. */
  start(request: JobRequest, options?: RequestOptions): Promise<JobSnapshot>;
  get(jobId: string, options?: RequestOptions): Promise<JobSnapshot>;
  list(pageSize?: number, offset?: number, options?: RequestOptions): Promise<JobListPayload>;
  history(
    jobId: string,
    pageSize?: number,
    afterVersion?: number,
    options?: RequestOptions,
  ): Promise<JobHistoryPayload>;
  /** POST /api/jobs/{id}/cancel → 202 со снимком в состоянии cancelling. */
  cancel(jobId: string, options?: RequestOptions): Promise<JobSnapshot>;
}

export function createJobsApi(client: LntApiClient): JobsApi {
  const jobPath = (jobId: string, suffix = "") => `/api/jobs/${encodeURIComponent(jobId)}${suffix}`;
  return {
    start: (request, options = {}) =>
      snapshotFrom(
        client.requestJson("POST", "/api/jobs", request, { ...options, mutation: true }),
      ),
    get: (jobId, options = {}) =>
      snapshotFrom(client.requestJson("GET", jobPath(jobId), undefined, options)),
    list: async (pageSize = 50, offset = 0, options = {}) => {
      const params = new URLSearchParams({
        page_size: String(pageSize),
        offset: String(offset),
      });
      const payload = await client.requestJson("GET", `/api/jobs?${params}`, undefined, options);
      if (!isJobListPayload(payload)) throw new ApiError("parse");
      return payload;
    },
    history: async (jobId, pageSize = 100, afterVersion = 0, options = {}) => {
      const params = new URLSearchParams({
        page_size: String(pageSize),
        after_version: String(afterVersion),
      });
      const payload = await client.requestJson(
        "GET",
        `${jobPath(jobId, "/history")}?${params}`,
        undefined,
        options,
      );
      if (!isJobListPayload(payload)) throw new ApiError("parse");
      return payload;
    },
    cancel: (jobId, options = {}) =>
      snapshotFrom(
        client.requestJson("POST", jobPath(jobId, "/cancel"), undefined, {
          ...options,
          mutation: true,
        }),
      ),
  };
}

export interface PlotsApi {
  detail(name: string, options?: RequestOptions): Promise<SessionDetailPayload>;
  spectrum(name: string, maxPoints?: number, options?: RequestOptions): Promise<SpectrumPayload>;
  waveform(
    name: string,
    channel?: WaveformChannel,
    maxPoints?: number,
    options?: RequestOptions,
  ): Promise<WaveformPayload>;
}

export function createPlotsApi(client: LntApiClient): PlotsApi {
  const sessionPath = (name: string, suffix = "") =>
    `/api/sessions/${encodeURIComponent(name)}${suffix}`;
  return {
    detail: async (name, options = {}) => {
      const payload = await client.requestJson("GET", sessionPath(name), undefined, options);
      if (!isSessionDetailPayload(payload)) throw new ApiError("parse");
      return payload;
    },
    spectrum: async (name, maxPoints = 5_000, options = {}) => {
      const params = new URLSearchParams({ max_points: String(maxPoints) });
      const payload = await client.requestJson(
        "GET",
        `${sessionPath(name, "/spectrum")}?${params}`,
        undefined,
        options,
      );
      if (!isSpectrumPayload(payload)) throw new ApiError("parse");
      return payload;
    },
    waveform: async (name, channel = "ch1", maxPoints = 4_000, options = {}) => {
      const params = new URLSearchParams({ channel, max_points: String(maxPoints) });
      const payload = await client.requestJson(
        "GET",
        `${sessionPath(name, "/waveform")}?${params}`,
        undefined,
        options,
      );
      if (!isWaveformPayload(payload)) throw new ApiError("parse");
      return payload;
    },
  };
}
