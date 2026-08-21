/** Доменный под-клиент исследовательского контура v2 (Todo 34):
 * эксперименты, запуски протоколов, гипотезы, тренды и сравнимость.
 * Маршруты: routes_experiments.py, routes_research.py, routes_quality.py.
 * Все мутации подписываются nonce запуска (middleware требует его на
 * каждый POST/PUT/PATCH/DELETE); конверты проверяются перед выдачей. */

import type { LntApiClient, RequestOptions } from "./client";
import { ApiError } from "./errors";
import type {
  ComparabilityPairRequest,
  ComparabilityReport,
  CursorPage,
  ExperimentRecord,
  ExperimentWritePayload,
  HypothesisListQuery,
  HypothesisRecord,
  HypothesisWritePayload,
  OpenRecord,
  ProtocolRunRecord,
  RunConfirmPayload,
  RunStartPayload,
  TrendAnalysisResult,
  TrendQueryRequest,
} from "./types-research";

const V2 = "/api/v2";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

type ItemAssert<T> = (item: Record<string, unknown>) => T;

function assertOpen(item: Record<string, unknown>): OpenRecord {
  return item;
}

function assertExperiment(item: Record<string, unknown>): ExperimentRecord {
  if (typeof item.experiment_id !== "string") throw new ApiError("parse");
  return item as ExperimentRecord;
}

function assertHypothesis(item: Record<string, unknown>): HypothesisRecord {
  if (
    typeof item.hypothesis_id !== "string" ||
    typeof item.revision !== "number" ||
    typeof item.status !== "string"
  ) {
    throw new ApiError("parse");
  }
  return item as HypothesisRecord;
}

function requireCursorPage<T>(payload: unknown, assertItem: ItemAssert<T>): CursorPage<T> {
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiError("parse");
  const { next_cursor } = payload;
  if (next_cursor !== null && typeof next_cursor !== "string") throw new ApiError("parse");
  return {
    items: payload.items.map((item) => {
      if (!isRecord(item)) throw new ApiError("parse");
      return assertItem(item);
    }),
    next_cursor,
  };
}

function requireRun(payload: unknown): ProtocolRunRecord {
  if (!isRecord(payload)) throw new ApiError("parse");
  if (
    typeof payload.run_id !== "string" ||
    typeof payload.status !== "string" ||
    typeof payload.revision !== "number"
  ) {
    throw new ApiError("parse");
  }
  return payload as ProtocolRunRecord;
}

function requireTrendResult(payload: unknown): TrendAnalysisResult {
  if (!isRecord(payload)) throw new ApiError("parse");
  const stamps = payload.normalized_timestamps;
  if (!Array.isArray(stamps) || !stamps.every((item) => typeof item === "string")) {
    throw new ApiError("parse");
  }
  const meta = payload.metadata;
  if (
    !isRecord(meta) ||
    typeof meta.units !== "string" ||
    typeof meta.estimator !== "string" ||
    typeof meta.n !== "number"
  ) {
    throw new ApiError("parse");
  }
  return payload as TrendAnalysisResult;
}

function requireComparabilityReport(payload: unknown): ComparabilityReport {
  if (!isRecord(payload)) throw new ApiError("parse");
  if (
    typeof payload.comparable !== "boolean" ||
    !Array.isArray(payload.findings) ||
    !payload.findings.every((item) => isRecord(item))
  ) {
    throw new ApiError("parse");
  }
  return payload as unknown as ComparabilityReport;
}

export interface ResearchApi {
  experiments(
    pageSize?: number,
    cursor?: string | null,
    options?: RequestOptions,
  ): Promise<CursorPage<ExperimentRecord>>;
  experiment(experimentId: string, options?: RequestOptions): Promise<ExperimentRecord>;
  createExperiment(
    payload: ExperimentWritePayload,
    options?: RequestOptions,
  ): Promise<ExperimentRecord>;
  updateExperiment(
    experimentId: string,
    payload: ExperimentWritePayload,
    options?: RequestOptions,
  ): Promise<ExperimentRecord>;
  revisions(
    id: string,
    pageSize?: number,
    cursor?: string | null,
    options?: RequestOptions,
  ): Promise<CursorPage<OpenRecord>>;
  members(
    id: string,
    pageSize?: number,
    cursor?: string | null,
    options?: RequestOptions,
  ): Promise<CursorPage<OpenRecord>>;
  steps(
    id: string,
    pageSize?: number,
    cursor?: string | null,
    options?: RequestOptions,
  ): Promise<CursorPage<OpenRecord>>;
  startRun(
    experimentId: string,
    payload: RunStartPayload,
    options?: RequestOptions,
  ): Promise<ProtocolRunRecord>;
  runStatus(runId: string, options?: RequestOptions): Promise<ProtocolRunRecord>;
  confirmRun(
    runId: string,
    payload: RunConfirmPayload,
    options?: RequestOptions,
  ): Promise<ProtocolRunRecord>;
  resumeRun(runId: string, options?: RequestOptions): Promise<ProtocolRunRecord>;
  cancelRun(runId: string, options?: RequestOptions): Promise<ProtocolRunRecord>;
  hypotheses(
    query?: HypothesisListQuery,
    options?: RequestOptions,
  ): Promise<CursorPage<HypothesisRecord>>;
  hypothesis(hypothesisId: string, options?: RequestOptions): Promise<HypothesisRecord>;
  createHypothesis(
    payload: HypothesisWritePayload,
    options?: RequestOptions,
  ): Promise<HypothesisRecord>;
  updateHypothesis(
    hypothesisId: string,
    payload: HypothesisWritePayload,
    options?: RequestOptions,
  ): Promise<HypothesisRecord>;
  queryTrends(request: TrendQueryRequest, options?: RequestOptions): Promise<TrendAnalysisResult>;
  comparabilityCheck(
    pair: ComparabilityPairRequest,
    options?: RequestOptions,
  ): Promise<ComparabilityReport>;
}

export function createResearchApi(client: LntApiClient): ResearchApi {
  async function page<T>(
    path: string,
    pageSize: number | undefined,
    cursor: string | null | undefined,
    options: RequestOptions,
    assertItem: ItemAssert<T>,
  ): Promise<CursorPage<T>> {
    const params = new URLSearchParams();
    if (pageSize !== undefined) params.set("page_size", String(pageSize));
    if (cursor) params.set("cursor", cursor);
    const qs = params.toString();
    const payload = await client.requestJson(
      "GET",
      `${path}${qs ? `?${qs}` : ""}`,
      undefined,
      options,
    );
    return requireCursorPage(payload, assertItem);
  }

  const experimentPath = (id: string, suffix = "") =>
    `${V2}/experiments/${encodeURIComponent(id)}${suffix}`;
  const runPath = (runId: string, suffix = "") =>
    `${V2}/protocol-runs/${encodeURIComponent(runId)}${suffix}`;
  const mutation = (options: RequestOptions): RequestOptions & { mutation: boolean } => ({
    ...options,
    mutation: true,
  });

  return {
    experiments: (pageSize, cursor, options = {}) =>
      page(`${V2}/experiments`, pageSize, cursor, options, assertExperiment),
    experiment: async (experimentId, options = {}) => {
      const payload = await client.requestJson(
        "GET",
        experimentPath(experimentId),
        undefined,
        options,
      );
      return assertExperiment(
        isRecord(payload)
          ? payload
          : (() => {
              throw new ApiError("parse");
            })(),
      );
    },
    createExperiment: async (payload, options = {}) => {
      const created = await client.requestJson(
        "POST",
        `${V2}/experiments`,
        payload,
        mutation(options),
      );
      return assertExperiment(
        isRecord(created)
          ? created
          : (() => {
              throw new ApiError("parse");
            })(),
      );
    },
    updateExperiment: async (experimentId, payload, options = {}) => {
      const updated = await client.requestJson(
        "PUT",
        experimentPath(experimentId),
        payload,
        mutation(options),
      );
      return assertExperiment(
        isRecord(updated)
          ? updated
          : (() => {
              throw new ApiError("parse");
            })(),
      );
    },
    revisions: (id, pageSize, cursor, options = {}) =>
      page(experimentPath(id, "/revisions"), pageSize, cursor, options, assertOpen),
    members: (id, pageSize, cursor, options = {}) =>
      page(experimentPath(id, "/members"), pageSize, cursor, options, assertOpen),
    steps: (id, pageSize, cursor, options = {}) =>
      page(experimentPath(id, "/steps"), pageSize, cursor, options, assertOpen),
    startRun: async (experimentId, payload, options = {}) =>
      requireRun(
        await client.requestJson(
          "POST",
          experimentPath(experimentId, "/runs"),
          payload,
          mutation(options),
        ),
      ),
    runStatus: async (runId, options = {}) =>
      requireRun(await client.requestJson("GET", runPath(runId), undefined, options)),
    confirmRun: async (runId, payload, options = {}) =>
      requireRun(
        await client.requestJson("POST", runPath(runId, "/confirm"), payload, mutation(options)),
      ),
    resumeRun: async (runId, options = {}) =>
      requireRun(
        await client.requestJson("POST", runPath(runId, "/resume"), undefined, mutation(options)),
      ),
    cancelRun: async (runId, options = {}) =>
      requireRun(
        await client.requestJson("POST", runPath(runId, "/cancel"), undefined, mutation(options)),
      ),
    hypotheses: async (query = {}, options = {}) => {
      const params = new URLSearchParams();
      if (query.page_size !== undefined) params.set("page_size", String(query.page_size));
      if (query.cursor) params.set("cursor", query.cursor);
      if (query.status) params.set("status", query.status);
      const qs = params.toString();
      const payload = await client.requestJson(
        "GET",
        `${V2}/hypotheses${qs ? `?${qs}` : ""}`,
        undefined,
        options,
      );
      return requireCursorPage(payload, assertHypothesis);
    },
    hypothesis: async (hypothesisId, options = {}) => {
      const payload = await client.requestJson(
        "GET",
        `${V2}/hypotheses/${encodeURIComponent(hypothesisId)}`,
        undefined,
        options,
      );
      return assertHypothesis(
        isRecord(payload)
          ? payload
          : (() => {
              throw new ApiError("parse");
            })(),
      );
    },
    createHypothesis: async (payload, options = {}) => {
      const created = await client.requestJson(
        "POST",
        `${V2}/hypotheses`,
        payload,
        mutation(options),
      );
      return assertHypothesis(
        isRecord(created)
          ? created
          : (() => {
              throw new ApiError("parse");
            })(),
      );
    },
    updateHypothesis: async (hypothesisId, payload, options = {}) => {
      const updated = await client.requestJson(
        "PUT",
        `${V2}/hypotheses/${encodeURIComponent(hypothesisId)}`,
        payload,
        mutation(options),
      );
      return assertHypothesis(
        isRecord(updated)
          ? updated
          : (() => {
              throw new ApiError("parse");
            })(),
      );
    },
    queryTrends: async (request, options = {}) =>
      requireTrendResult(
        await client.requestJson("POST", `${V2}/trends/query`, request, mutation(options)),
      ),
    comparabilityCheck: async (pair, options = {}) =>
      requireComparabilityReport(
        await client.requestJson("POST", `${V2}/comparability/check`, pair, mutation(options)),
      ),
  };
}
