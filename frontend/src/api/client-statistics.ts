/** Под-клиент статистики v2 (todo 43): durable statistics-runs из
 * routes_statistics.py (todo 31). POST ставит задачу (202 + JobSnapshot),
 * GET /result отдаёт 202-снимок, готовый результат или 422 {code, detail}
 * при отказе расчёта. Контракты сверены с бэкендом, эндпоинты не выдуманы. */

import type { LntApiClient, RequestOptions } from "./client";
import { ApiError } from "./errors";
import type {
  JobSnapshotPayload,
  StatisticsResultEnvelope,
  StatisticsRunRequest,
} from "./types-research";

const V2 = "/api/v2";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function requireSnapshot(payload: unknown): JobSnapshotPayload {
  if (
    !isRecord(payload) ||
    typeof payload.job_id !== "string" ||
    typeof payload.status !== "string" ||
    typeof payload.version !== "number"
  ) {
    throw new ApiError("parse");
  }
  return payload as unknown as JobSnapshotPayload;
}

/** Готовый результат: конверт с result_kind effect|descriptive|refusal. */
function requireResult(payload: unknown): StatisticsResultEnvelope {
  if (
    !isRecord(payload) ||
    !isRecord(payload.metadata) ||
    typeof payload.result_kind !== "string"
  ) {
    throw new ApiError("parse");
  }
  if (!["effect", "descriptive", "refusal"].includes(payload.result_kind)) {
    throw new ApiError("parse");
  }
  if (!isRecord(payload.result)) throw new ApiError("parse");
  return payload as unknown as StatisticsResultEnvelope;
}

export interface StatisticsApi {
  /** POST /experiments/{id}/statistics-runs → 202 JobSnapshot. */
  submit(
    experimentId: string,
    request: StatisticsRunRequest,
    options?: RequestOptions,
  ): Promise<JobSnapshotPayload>;
  /** GET /statistics-runs/{jobId}/result: pending → snapshot, ready → envelope. */
  result(
    jobId: string,
    options?: RequestOptions,
  ): Promise<JobSnapshotPayload | StatisticsResultEnvelope>;
}

export function createStatisticsApi(client: LntApiClient): StatisticsApi {
  const mutation = (options: RequestOptions): RequestOptions & { mutation: boolean } => ({
    ...options,
    mutation: true,
  });
  return {
    submit: async (experimentId, request, options = {}) =>
      requireSnapshot(
        await client.requestJson(
          "POST",
          `${V2}/experiments/${encodeURIComponent(experimentId)}/statistics-runs`,
          request,
          mutation(options),
        ),
      ),
    result: async (jobId, options = {}) => {
      // 202 и 200 разбираются requestJson одинаково; форма тела различает исход.
      const payload = await client.requestJson(
        "GET",
        `${V2}/statistics-runs/${encodeURIComponent(jobId)}/result`,
        undefined,
        options,
      );
      if (isRecord(payload) && typeof payload.status === "string") return requireSnapshot(payload);
      return requireResult(payload);
    },
  };
}
