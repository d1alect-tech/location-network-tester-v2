import type { Page, Route } from "@playwright/test";
import type { DeviceStateValue, PreflightResponse } from "../api/types-device";
import type { JobSnapshot } from "../api/types-jobs";
import {
  BUILD_ID,
  DEVICE_TEXTS,
  NONCE,
  buildJobScript,
  configPayload,
  json,
  snap,
  sseBody,
} from "./mock-fixtures";

/** Мок-бэкенд LNT для e2e: маршрутизатор с точными контрактами routes_jobs.py
 * и routes_device.py. Продуктовый бэкенд не меняется — перехватывается только
 * сетевой слой Playwright.
 *
 * Темп событий задачи управляется тестом: pump()/pumpAll() перекладывают
 * следующий сценарный снимок в очередь SSE; без этого поток отдаёт пустой
 * кадр с retry — детерминированно и без гонок. */

export interface MockOptions {
  deviceState?: DeviceStateValue;
  /** Задача, уже существующая на сервере при монтировании (восстановление). */
  existingJob?: JobSnapshot;
}

export interface JobPlan {
  /** Сценарные снимки, ожидающие pump(). */
  scripted: JobSnapshot[];
  /** Готовые к доставке в SSE. */
  ready: JobSnapshot[];
  lastDelivered: JobSnapshot;
}

export interface MockBackend {
  /** Тела запросов POST /api/jobs по порядку поступления. */
  startedRequests: Record<string, unknown>[];
  preflightRequests: Record<string, unknown>[];
  cancelRequests: string[];
  plans: Map<string, JobPlan>;
  sessionCounter: number;
  /** Передаёт следующий сценарный снимок в поток SSE. */
  pump(jobId?: string): void;
  /** Передаёт все оставшиеся сценарные снимки сразу. */
  pumpAll(): void;
}

function preflightFindings(
  deviceState: DeviceStateValue,
  body: Record<string, unknown>,
): PreflightResponse["findings"] {
  const findings: PreflightResponse["findings"] = [];
  if (deviceState !== "ready") {
    findings.push({
      severity: "block",
      code: `device_${deviceState}`,
      message_ru: `Устройство не готово: ${deviceState}.`,
      recovery_action_ru:
        "Выполните указанное диагностикой устройства действие и повторите preflight.",
    });
  }
  if (body.input === "transformer" && body.channels !== 1) {
    findings.push({
      severity: "block",
      code: "line_quality_requires_single_channel",
      message_ru: "Line-quality использует один трансформаторный канал CH1.",
      recovery_action_ru: "Выберите одноканальный режим; preflight не меняет его автоматически.",
    });
  }
  if (body.input === "transformer" && Number(body.range_v) < 5) {
    findings.push({
      severity: "warn",
      code: "line_quality_clipping_likely",
      message_ru: "Пик вторички около 16 В при пробнике 10x может перегрузить выбранный диапазон.",
      recovery_action_ru: "Выберите диапазон 5 В вручную; preflight не меняет настройку.",
    });
  }
  return findings;
}

async function startJob(route: Route, backend: MockBackend): Promise<void> {
  const body = route.request().postDataJSON() as Record<string, unknown>;
  if (route.request().headers()["x-lnt-mutation-nonce"] !== NONCE) {
    await route.fulfill(
      json({ code: "mutation_nonce_invalid", detail: "nonce недействителен" }, 403),
    );
    return;
  }
  backend.startedRequests.push(body);
  const jobId = `job-${backend.plans.size + 1}`;
  backend.sessionCounter += 1;
  const script = buildJobScript(body, jobId, backend.sessionCounter);
  // Первый запуск всегда отдаёт queued + первый рабочий снимок автоматически.
  backend.plans.set(jobId, {
    scripted: script.scripted,
    ready: script.runningSnap !== undefined ? [script.first, script.runningSnap] : [script.first],
    lastDelivered: script.first,
  });
  await route.fulfill(json(script.first, 202));
}

async function handleJobRoute(
  route: Route,
  backend: MockBackend,
  jobId: string,
  suffix: string,
): Promise<boolean> {
  const method = route.request().method();
  const plan = backend.plans.get(jobId);
  if (suffix === "/events" && method === "GET") {
    if (!plan) {
      await route.fulfill(json({ code: "unknown_job", detail: "задача неизвестна" }, 404));
      return true;
    }
    if (plan.ready.length === 0) {
      // События ещё не готовы (ждут pump или отмены).
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: "retry: 150\n\n",
      });
      return true;
    }
    const pending = [...plan.ready];
    plan.ready.length = 0;
    plan.lastDelivered = pending[pending.length - 1] ?? plan.lastDelivered;
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: sseBody(pending) });
    return true;
  }
  if (suffix === "/cancel" && method === "POST") {
    backend.cancelRequests.push(jobId);
    if (!plan) {
      await route.fulfill(json({ code: "unknown_job", detail: "задача неизвестна" }, 404));
      return true;
    }
    const base = plan.lastDelivered;
    // ВАЖНО: version из base не прокидывается спредом — он перебил бы новый номер.
    const { version: _baseVersion, ...rest } = base;
    void _baseVersion;
    const cancelling = snap(base.version + 1, { ...rest, status: "cancelling" });
    const cancelled = snap(base.version + 2, { ...rest, status: "cancelled", result: null });
    // Остаток сценария аннулируется: отмена прерывает серию на безопасной границе.
    plan.scripted.length = 0;
    plan.ready.push(cancelling, cancelled);
    await route.fulfill(json(cancelling, 202));
    return true;
  }
  if (suffix === "" && method === "GET") {
    if (!plan) {
      await route.fulfill(json({ code: "unknown_job", detail: "задача неизвестна" }, 404));
      return true;
    }
    await route.fulfill(json(plan.lastDelivered));
    return true;
  }
  if (suffix === "/history" && method === "GET") {
    await route.fulfill(json({ items: plan ? [plan.lastDelivered] : [] }));
    return true;
  }
  return false;
}

async function handleApi(route: Route, backend: MockBackend, options: MockOptions): Promise<void> {
  const url = new URL(route.request().url());
  const path = url.pathname;
  const method = route.request().method();

  if (path === "/api/config" && method === "GET") {
    await route.fulfill(json(configPayload()));
    return;
  }
  if (path === "/api/health" && method === "GET") {
    await route.fulfill(json({ status: "ok", build_id: BUILD_ID }));
    return;
  }
  if (path === "/api/device/state" && method === "GET") {
    const state = options.deviceState ?? "ready";
    await route.fulfill(json({ state, ...DEVICE_TEXTS[state] }));
    return;
  }
  if (path === "/api/capture/preflight" && method === "POST") {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    backend.preflightRequests.push(body);
    const deviceState: DeviceStateValue = options.deviceState ?? "ready";
    const findings = preflightFindings(deviceState, body);
    await route.fulfill(
      json({
        ready: !findings.some((finding) => finding.severity === "block"),
        device_state: deviceState,
        findings,
      }),
    );
    return;
  }
  if (path === "/api/jobs" && method === "POST") {
    await startJob(route, backend);
    return;
  }

  const jobMatch = path.match(/^\/api\/jobs\/([^/]+)(\/.*)?$/);
  if (jobMatch !== null) {
    const handled = await handleJobRoute(route, backend, jobMatch[1] as string, jobMatch[2] ?? "");
    if (handled) return;
  }

  if (path === "/api/jobs" && method === "GET") {
    await route.fulfill(json({ items: options.existingJob ? [options.existingJob] : [] }));
    return;
  }
  if (method === "GET") {
    if (path.startsWith("/api/catalog/sessions")) {
      await route.fulfill(json({ items: [], next_cursor: null }));
      return;
    }
    await route.fulfill(json({}));
    return;
  }
  await route.fulfill(json({ code: "not_found", detail: path }, 404));
}

export function installMockBackend(page: Page, options: MockOptions = {}): MockBackend {
  const backend: MockBackend = {
    startedRequests: [],
    preflightRequests: [],
    cancelRequests: [],
    plans: new Map(),
    sessionCounter: 0,
    pump: (jobId) => {
      for (const [id, plan] of backend.plans) {
        if (jobId !== undefined && id !== jobId) continue;
        const next = plan.scripted.shift();
        if (next !== undefined) plan.ready.push(next);
      }
    },
    pumpAll: () => {
      for (const plan of backend.plans.values()) {
        while (plan.scripted.length > 0) {
          const next = plan.scripted.shift();
          if (next !== undefined) plan.ready.push(next);
        }
      }
    },
  };

  // Точный предикат вместо glob "**/api/**": тот матчил и модули vite вида
  // /static/v2/src/api/*.ts и ломал загрузку приложения JSON-ответом.
  page.route(
    (url) => url.pathname.startsWith("/api/") || url.pathname === "/api",
    (route) => void handleApi(route, backend, options),
  );

  return backend;
}
