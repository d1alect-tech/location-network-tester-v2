import type { LntApiClient, RequestOptions } from "./client";
import { requireRun } from "./client-research-guards";
import { experimentPath, mutation, runPath } from "./client-research-paths";
import type { ProtocolRunRecord, RunConfirmPayload, RunStartPayload } from "./types-research";

export interface RunsResearchGroup {
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
}

export function createRunsGroup(client: LntApiClient): RunsResearchGroup {
  return {
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
  };
}
