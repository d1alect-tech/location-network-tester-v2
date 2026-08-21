/** Fetch-клиент стабильных контрактов LNT: nonce запуска, контроль build id,
 * нормализация ошибок. Заголовок мутаций: X-LNT-Mutation-Nonce (security.py). */

import { createJobsApi, createPlotsApi } from "./client-jobs";
import type { JobsApi, PlotsApi } from "./client-jobs";
import { createResearchApi } from "./client-research";
import type { ResearchApi } from "./client-research";
import { ApiError, isAbortError, normalizeThrown, parseApiError } from "./errors";
import {
  isCatalogPage,
  isConfigPayload,
  isContextResponse,
  isHealthPayload,
  isProfileList,
} from "./guards";
import type {
  CatalogPage,
  CatalogQuery,
  ConfigPayload,
  ContextResponse,
  ContextUpdateRequest,
  HealthPayload,
  LegacySessionsPayload,
  ProfileList,
} from "./types";

export interface RequestOptions {
  signal?: AbortSignal;
}

const MUTATION_NONCE_HEADER = "X-LNT-Mutation-Nonce";

export class LntApiClient {
  private buildId: string | null = null;
  private nonce: string | null = null;

  /** Задачи панели (Todos 14–18): запуск, снимки, отмена, история. */
  readonly jobs: JobsApi;
  /** Графики и детали сессии (Todo 27). */
  readonly plots: PlotsApi;
  /** Эксперименты, гипотезы, тренды, сравнимость (Todo 34). */
  readonly research: ResearchApi;

  constructor(private readonly fetchImpl: typeof fetch = (...args) => fetch(...args)) {
    this.jobs = createJobsApi(this);
    this.plots = createPlotsApi(this);
    this.research = createResearchApi(this);
  }

  get currentBuildId(): string | null {
    return this.buildId;
  }

  get currentNonce(): string | null {
    return this.nonce;
  }

  /** Первичная загрузка /api/config: запоминает build_id и nonce запуска. */
  async bootstrap(options: RequestOptions = {}): Promise<ConfigPayload> {
    const config = await this.getConfig(options);
    this.buildId = config.build_id;
    this.nonce = config.mutation_nonce;
    return config;
  }

  /** Детерминированное восстановление после перезапуска сервера/обновления. */
  async recover(options: RequestOptions = {}): Promise<ConfigPayload> {
    return this.bootstrap(options);
  }

  async health(options: RequestOptions = {}): Promise<HealthPayload> {
    const payload = await this.requestJson("GET", "/api/health", undefined, options);
    if (!isHealthPayload(payload)) throw new ApiError("parse");
    return payload;
  }

  /** Сверяет build id сервера с известным; расхождение → build_mismatch. */
  async verifyBuild(options: RequestOptions = {}): Promise<void> {
    const { build_id } = await this.health(options);
    if (this.buildId !== null && build_id !== this.buildId) {
      throw new ApiError("build_mismatch", { code: "build_id_changed" });
    }
  }

  async catalogSessions(
    query: CatalogQuery = {},
    options: RequestOptions = {},
  ): Promise<CatalogPage> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === false || value === "") continue;
      params.set(key, String(value));
    }
    const qs = params.toString();
    const payload = await this.requestJson(
      "GET",
      `/api/catalog/sessions${qs ? `?${qs}` : ""}`,
      undefined,
      options,
    );
    if (!isCatalogPage(payload)) throw new ApiError("parse");
    return payload;
  }

  async context(sessionId: string, options: RequestOptions = {}): Promise<ContextResponse> {
    const payload = await this.requestJson(
      "GET",
      `/api/context/${encodeURIComponent(sessionId)}`,
      undefined,
      options,
    );
    if (!isContextResponse(payload)) throw new ApiError("parse");
    return payload;
  }

  async updateContext(
    sessionId: string,
    request: ContextUpdateRequest,
    options: RequestOptions = {},
  ): Promise<ContextResponse> {
    const payload = await this.requestJson(
      "PUT",
      `/api/context/${encodeURIComponent(sessionId)}`,
      request,
      { ...options, mutation: true },
    );
    if (!isContextResponse(payload)) throw new ApiError("parse");
    return payload;
  }

  async profiles(options: RequestOptions = {}): Promise<ProfileList> {
    const payload = await this.requestJson("GET", "/api/profiles", undefined, options);
    if (!isProfileList(payload)) throw new ApiError("parse");
    return payload;
  }

  async legacySessions(options: RequestOptions = {}): Promise<LegacySessionsPayload> {
    return this.requestJson(
      "GET",
      "/api/sessions",
      undefined,
      options,
    ) as Promise<LegacySessionsPayload>;
  }

  private getConfig(options: RequestOptions): Promise<ConfigPayload> {
    // bootstrap читает сырой JSON: guard применяется вызывающей стороной ниже.
    return this.requestJson("GET", "/api/config", undefined, options).then((payload) => {
      if (!isConfigPayload(payload)) throw new ApiError("parse");
      return payload;
    });
  }

  private requireNonce(): string {
    if (this.nonce === null) {
      throw new ApiError("uninitialized", { code: "nonce_missing" });
    }
    return this.nonce;
  }

  /** Единая точка HTTP для доменных под-клиентов (jobs/plots/research). */
  async requestJson(
    method: "GET" | "PUT" | "POST" | "DELETE",
    path: string,
    body: unknown,
    options: RequestOptions & { mutation?: boolean },
  ): Promise<unknown> {
    let response: Response;
    try {
      const headers: Record<string, string> = {};
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (options.mutation) headers[MUTATION_NONCE_HEADER] = this.requireNonce();
      response = await this.fetchImpl(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: options.signal,
      });
    } catch (error) {
      if (isAbortError(error)) throw error;
      throw normalizeThrown(error);
    }
    if (!response.ok) {
      throw parseApiError(response.status, await safeJsonBody(response));
    }
    try {
      return await response.json();
    } catch (error) {
      throw new ApiError("parse", { cause: error });
    }
  }
}

async function safeJsonBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}
