import type { LntApiClient, RequestOptions } from "./client";
import {
  assertHypothesis,
  isRecord,
  requireComparabilityReport,
  requireCursorPage,
  requireTrendResult,
} from "./client-research-guards";
import { V2, mutation } from "./client-research-paths";
import { ApiError } from "./errors";
import type {
  ComparabilityPairRequest,
  ComparabilityReport,
  CursorPage,
  HypothesisListQuery,
  HypothesisRecord,
  HypothesisWritePayload,
  TrendAnalysisResult,
  TrendQueryRequest,
} from "./types-research";

export interface HypothesesResearchGroup {
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

export function createHypothesesGroup(client: LntApiClient): HypothesesResearchGroup {
  return {
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
