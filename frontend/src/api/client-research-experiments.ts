import type { LntApiClient, RequestOptions } from "./client";
import { assertExperiment, assertOpen, isRecord } from "./client-research-guards";
import { V2, experimentPath, fetchPage, mutation } from "./client-research-paths";
import { ApiError } from "./errors";
import type {
  CursorPage,
  ExperimentRecord,
  ExperimentWritePayload,
  OpenRecord,
} from "./types-research";

export interface ExperimentsResearchGroup {
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
}

export function createExperimentsGroup(client: LntApiClient): ExperimentsResearchGroup {
  return {
    experiments: (pageSize, cursor, options = {}) =>
      fetchPage(client, `${V2}/experiments`, pageSize, cursor, options, assertExperiment),
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
      fetchPage(client, experimentPath(id, "/revisions"), pageSize, cursor, options, assertOpen),
    members: (id, pageSize, cursor, options = {}) =>
      fetchPage(client, experimentPath(id, "/members"), pageSize, cursor, options, assertOpen),
    steps: (id, pageSize, cursor, options = {}) =>
      fetchPage(client, experimentPath(id, "/steps"), pageSize, cursor, options, assertOpen),
  };
}
