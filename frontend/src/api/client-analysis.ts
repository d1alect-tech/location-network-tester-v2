/** Под-клиент артефактов анализа v2 (todo 42): бинарный NPZ и events.json.
 * Бинарные ответы requestJson не покрывает (он только JSON), поэтому fetch
 * здесь отдельный — с той же нормализацией ошибок и AbortSignal. */

import type { LntApiClient, RequestOptions } from "./client";
import { ApiError, isAbortError, normalizeThrown, parseApiError } from "./errors";
import { isEventInventoryPayload, isRecipeListPayload } from "./guards-analysis";
import type { AnalysisRecipePayload, EventInventoryPayload } from "./types-analysis";

function artifactPath(session: string, key: string, suffix: string): string {
  return `/api/analysis/sessions/${encodeURIComponent(session)}/artifacts/${encodeURIComponent(
    key,
  )}${suffix}`;
}

export interface AnalysisApi {
  /** GET …/artifacts/{key}/{filename} → байты (например spectrogram.npz). */
  artifactBytes(
    session: string,
    key: string,
    filename: string,
    options?: RequestOptions,
  ): Promise<ArrayBuffer>;
  /** GET …/artifacts/{key}/events.json → проверенная инвентаризация событий. */
  events(session: string, key: string, options?: RequestOptions): Promise<EventInventoryPayload>;
  /** GET /api/analysis/recipes → неизменяемые рецепты (только чтение). */
  recipes(options?: RequestOptions): Promise<AnalysisRecipePayload[]>;
}

export function createAnalysisApi(client: LntApiClient): AnalysisApi {
  async function requestBinary(path: string, options: RequestOptions): Promise<ArrayBuffer> {
    let response: Response;
    try {
      response = await client.rawFetch(path, { method: "GET", signal: options.signal });
    } catch (error) {
      if (isAbortError(error)) throw error;
      throw normalizeThrown(error);
    }
    if (!response.ok) {
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        body = undefined;
      }
      throw parseApiError(response.status, body);
    }
    try {
      return await response.arrayBuffer();
    } catch (error) {
      throw new ApiError("parse", { cause: error });
    }
  }

  return {
    artifactBytes: (session, key, filename, options = {}) =>
      requestBinary(artifactPath(session, key, `/${encodeURIComponent(filename)}`), options),
    events: async (session, key, options = {}) => {
      const payload = await client.requestJson(
        "GET",
        artifactPath(session, key, "/events.json"),
        undefined,
        options,
      );
      if (!isEventInventoryPayload(payload)) throw new ApiError("parse");
      return payload;
    },
    recipes: async (options = {}) => {
      const payload = await client.requestJson("GET", "/api/analysis/recipes", undefined, options);
      if (!isRecipeListPayload(payload)) throw new ApiError("parse");
      return payload.items;
    },
  };
}
