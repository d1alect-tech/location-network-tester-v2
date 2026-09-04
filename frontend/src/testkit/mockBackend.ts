/** Единый мок-бэкенд LNT для e2e (только e2e/spec, не продукт).
 * Слит из трёх расходившихся моков: test-support/mock-lnt-backend.ts
 * (задачи + SSE pump), testkit/mockBackend.ts (каталог/контекст/профили),
 * testkit/researchBackend.ts (эксперименты/статистика/тренды). Числа —
 * только canned-золото mockGolden (корпус tests/science/corpus.py),
 * семантика aba.py в TS не дублируется.
 *
 * Предикат — startsWith(/api/) (glob **\/api/** ломал модули vite);
 * мутации требуют x-lnt-mutation-nonce из /api/config; темп SSE задаёт
 * тест через pump()/pumpAll(). Продуктовый бэкенд не меняется. */

import type { Page, Route } from "@playwright/test";
import type { CatalogSession } from "../api/types";
import type { DeviceStateValue } from "../api/types-device";
import type { JobSnapshot } from "../api/types-jobs";
import { CatalogStore, handleCatalog } from "./mockCatalogStore";
import { buildPreflight, devicePayload } from "./mockDevice";
import { BUILD_ID, type FixtureSession, NONCE, researchSessions } from "./mockGolden";
import { type MockHttpReply, type MockHttpRequest, isApiPath, stripStaticPrefix } from "./mockHttp";
import { JobStore, handleJobs } from "./mockJobStore";
import { ResearchStore, handleResearch } from "./mockResearchStore";

export interface MockBackendOptions {
  deviceState?: DeviceStateValue;
  /** Задача, уже существующая на сервере при монтировании (восстановление). */
  existingJob?: JobSnapshot;
  /** Размер генерируемого каталога (0 — только research-сессии). */
  catalogSize?: number;
  catalogSeed?: number;
}

interface ArtifactSeed {
  body: string | Buffer;
  contentType: string;
}

function defaultSpectrum(): Record<string, unknown> {
  const points = Array.from({ length: 32 }, (_, i) => 1000 * 2 ** (i / 4));
  return {
    frequency_hz: points,
    psd_v2_per_hz: points.map((f) => 1e-8 / (f / 1000)),
    point_count: points.length,
  };
}

export class MockLntBackend {
  readonly catalog = new CatalogStore(0);
  readonly jobs = new JobStore();
  readonly research = new ResearchStore();
  deviceState: DeviceStateValue = "ready";
  readonly preflightRequests: Record<string, unknown>[] = [];
  private readonly researchSessions: FixtureSession[];
  private readonly details = new Map<string, unknown>();
  private readonly spectra = new Map<string, unknown>();
  private readonly referred = new Map<string, { status: number; body: unknown }>();
  private readonly waveforms = new Map<string, unknown>();
  private readonly pointers = new Map<
    string,
    { recipe_id?: string; artifact_key: string } | null
  >();
  private readonly artifacts = new Map<string, ArtifactSeed>();

  constructor(options: MockBackendOptions = {}) {
    this.deviceState = options.deviceState ?? "ready";
    if (options.existingJob) this.jobs.existingJob = options.existingJob;
    const size = options.catalogSize ?? 0;
    if (size > 0) {
      const generated = new CatalogStore(size, options.catalogSeed ?? 39);
      this.catalog.seedCatalog([...generated.sessions]);
    }
    this.researchSessions = researchSessions();
  }

  // ---- хуки спек (имена сохранены от трёх старых моков) ----
  get startedRequests(): Record<string, unknown>[] {
    return this.jobs.startedRequests;
  }
  get cancelRequests(): string[] {
    return this.jobs.cancelRequests;
  }
  get plans(): JobStore["plans"] {
    return this.jobs.plans;
  }
  get sessionCounter(): number {
    return this.jobs.sessionCounter;
  }
  get conflictQueue(): Set<string> {
    return this.catalog.conflictQueue;
  }
  get conflictNextHypothesis(): boolean {
    return this.research.conflictNextHypothesis;
  }
  set conflictNextHypothesis(value: boolean) {
    this.research.conflictNextHypothesis = value;
  }
  get mixedTypeSessions(): Set<string> {
    return this.research.mixedTypeSessions;
  }
  pump(jobId?: string): void {
    this.jobs.pump(jobId);
  }
  pumpAll(): void {
    this.jobs.pumpAll();
  }
  getContext(sessionId: string): ReturnType<CatalogStore["getContext"]> {
    return this.catalog.getContext(sessionId);
  }
  concurrentEdit(sessionId: string): void {
    this.catalog.concurrentEdit(sessionId);
  }

  // ---- сиды inspect-фикстур спек (данные живут в спеках, не в мокe) ----
  seedCatalog(items: CatalogSession[]): void {
    this.catalog.seedCatalog(items);
  }
  seedSessionDetail(id: string, payload: unknown): void {
    this.details.set(id, payload);
  }
  seedSpectrum(id: string, payload: unknown): void {
    this.spectra.set(id, payload);
  }
  seedReferredSpectrum(id: string, payload: unknown, status = 200): void {
    this.referred.set(id, { status, body: payload });
  }
  seedWaveform(id: string, payload: unknown): void {
    this.waveforms.set(id, payload);
  }
  seedAnalysisPointer(
    sessionId: string,
    pointer: { recipe_id?: string; artifact_key: string } | null,
  ): void {
    this.pointers.set(sessionId, pointer);
  }
  seedArtifact(
    sessionId: string,
    key: string,
    filename: string,
    body: string | Buffer,
    contentType?: string,
  ): void {
    const resolvedType =
      contentType ?? (filename.endsWith(".csv") ? "text/csv" : "application/json");
    this.artifacts.set(`${sessionId}/${key}/${filename}`, { body, contentType: resolvedType });
  }

  configPayload(): Record<string, unknown> {
    return {
      root: "C:\\lnt-sessions-test",
      profiles: ["bad", "bad-damped", "quiet", "sync-only", "async-heavy"],
      defaults: {
        simulate: { duration_s: 2.4, sample_rate_hz: 500000, seed: 6022, repeat: 1, interval_s: 0 },
        capture: { duration_s: 2.4, sample_rate_hz: 8000000, range_v: 5, repeat: 1, interval_s: 0 },
        ranges: [5, 1, 0.5],
      },
      build_id: BUILD_ID,
      mutation_nonce: NONCE,
      static_asset_hash: "c2",
      static_assets: {},
    };
  }

  private sessionDetail(id: string): unknown | null {
    const seeded = this.details.get(id);
    if (seeded !== undefined) return seeded;
    const research = this.researchSessions.find((item) => item.id === id);
    if (research) {
      return {
        name: research.id,
        manifest: {},
        analysis: {
          metrics: { band_mid_total: research.metric },
          ch1_input_reference:
            research.health === "ok"
              ? { status: "available", model_kind: "rc_shunt_v1" }
              : { status: "unavailable", reason_code: "analysis_unavailable" },
        },
        spectrum_available: true,
        waveform_available: false,
        ch2_available: false,
      };
    }
    const catalogItem = this.catalog.sessions.find((item) => item.id === id);
    if (catalogItem) {
      return {
        name: catalogItem.id,
        manifest: {},
        analysis: {
          metrics: { band_mid_total: 0 },
          ch1_input_reference:
            catalogItem.health === "ok"
              ? { status: "available", model_kind: "rc_shunt_v1" }
              : { status: "unavailable", reason_code: "analysis_unavailable" },
        },
        spectrum_available: true,
        waveform_available: false,
        ch2_available: false,
      };
    }
    return null;
  }

  handleRequest(request: MockHttpRequest): MockHttpReply | null {
    const { method, path } = request;
    if (path === "/api/config" && method === "GET")
      return { status: 200, body: this.configPayload() };
    if (path === "/api/health" && method === "GET") {
      return { status: 200, body: { status: "ok", build_id: BUILD_ID } };
    }
    if (path === "/api/device/state" && method === "GET") {
      return { status: 200, body: devicePayload(this.deviceState) };
    }
    if (path === "/api/capture/preflight" && method === "POST") {
      const body = request.bodyJson<Record<string, unknown>>();
      this.preflightRequests.push(body);
      return { status: 200, body: buildPreflight(this.deviceState, body) };
    }
    const jobsReply = handleJobs(this.jobs, request);
    if (jobsReply) return jobsReply;
    if (path === "/api/catalog/sessions" && method === "GET") {
      if (this.catalog.sessions.length > 0)
        return { status: 200, body: this.catalog.catalog(request.searchParams) };
      return { status: 200, body: { items: this.researchSessions, next_cursor: null } };
    }
    const catalogReply = handleCatalog(this.catalog, request);
    if (catalogReply) return catalogReply;
    const researchReply = handleResearch(this.research, request);
    if (researchReply) return researchReply;
    return this.inspect(request);
  }

  private inspect(request: MockHttpRequest): MockHttpReply | null {
    const { method, path } = request;
    const sessionMatch = /^\/api\/sessions\/([^/]+)(\/.*)?$/.exec(path);
    if (sessionMatch) {
      const id = decodeURIComponent(sessionMatch[1] ?? "");
      const suffix = sessionMatch[2] ?? "";
      if (suffix === "" && method === "GET") {
        const detail = this.sessionDetail(id);
        return detail
          ? { status: 200, body: detail }
          : { status: 404, body: { detail: "сессия не найдена" } };
      }
      if (suffix === "/spectrum" && method === "GET") {
        return { status: 200, body: this.spectra.get(id) ?? defaultSpectrum() };
      }
      if (suffix === "/spectrum-input-referred" && method === "GET") {
        const seeded = this.referred.get(id);
        if (!seeded) return { status: 404, body: {} };
        return { status: seeded.status, body: seeded.body };
      }
      if (suffix === "/waveform" && method === "GET") {
        const wave = this.waveforms.get(id);
        return wave !== undefined
          ? { status: 200, body: wave }
          : { status: 404, body: { detail: "нет данных" } };
      }
      return null;
    }
    const pointerMatch = /^\/api\/analysis\/sessions\/([^/]+)\/\.lnt-default-analysis\.json$/.exec(
      path,
    );
    if (pointerMatch && method === "GET") {
      const id = decodeURIComponent(pointerMatch[1] ?? "");
      const pointer = this.pointers.get(id) ?? null;
      if (!pointer) return { status: 404, body: { detail: "нет указателя" } };
      return {
        status: 200,
        body: { recipe_id: pointer.recipe_id ?? "default", artifact_key: pointer.artifact_key },
      };
    }
    const artifactMatch = /^\/api\/analysis\/sessions\/([^/]+)\/artifacts\/([^/]+)\/(.+)$/.exec(
      path,
    );
    if (artifactMatch && method === "GET") {
      const key = `${decodeURIComponent(artifactMatch[1] ?? "")}/${decodeURIComponent(artifactMatch[2] ?? "")}/${decodeURIComponent(artifactMatch[3] ?? "")}`;
      const seed = this.artifacts.get(key);
      if (!seed) return { status: 404, body: { detail: "not found" } };
      return { status: 200, contentType: seed.contentType, body: seed.body };
    }
    return null;
  }

  async handle(route: Route): Promise<void> {
    const url = new URL(route.request().url());
    const path = stripStaticPrefix(url.pathname);
    const method = route.request().method();
    const request: MockHttpRequest = {
      method,
      path,
      searchParams: url.searchParams,
      nonceOk: route.request().headers()["x-lnt-mutation-nonce"] === NONCE,
      bodyJson<T>(): T {
        try {
          return (route.request().postDataJSON() ?? {}) as T;
        } catch {
          return {} as T;
        }
      },
    };
    const reply = this.handleRequest(request);
    if (!reply) {
      if (method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({}),
        });
        return;
      }
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: `нет мока: ${method} ${path}` }),
      });
      return;
    }
    await route.fulfill(toFulfill(reply));
  }
}

function toFulfill(reply: MockHttpReply): Parameters<Route["fulfill"]>[0] {
  if (typeof reply.body === "string" || Buffer.isBuffer(reply.body)) {
    return {
      status: reply.status,
      contentType: reply.contentType ?? "text/event-stream",
      body: reply.body,
    };
  }
  return {
    status: reply.status,
    contentType: reply.contentType ?? "application/json",
    body: reply.body === undefined ? "" : JSON.stringify(reply.body),
  };
}

/** Подключает единый бэкенд к Playwright page. Синхронный (как раньше):
 * спеки зовут без await и сразу пользуются backend.pumpAll(). */
export function installMockBackend(page: Page, options: MockBackendOptions = {}): MockLntBackend {
  const backend = new MockLntBackend(options);
  void page.route(
    (url) => isApiPath(url.pathname),
    (route) => void backend.handle(route),
  );
  return backend;
}
