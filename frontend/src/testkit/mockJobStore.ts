/** Задачи и SSE-поток единого мок-бэкенда (только e2e/spec).
 * Повторяет контракты routes_jobs.py: канонический JobSnapshot, сценарий
 * queued → running → analyzing → done, отмена на безопасной границе.
 * Темп событий управляет тест: pump()/pumpAll() перекладывают следующий
 * сценарный снимок в очередь SSE; без этого поток отдаёт пустой кадр
 * с retry — детерминированно и без гонок. */

import type { JobSnapshot } from "../api/types-jobs";
import {
  type MockHttpReply,
  type MockHttpRequest,
  failure,
  nonceRejected,
  notFound,
  ok,
} from "./mockHttp";

export interface JobPlan {
  /** Сценарные снимки, ожидающие pump(). */
  scripted: JobSnapshot[];
  /** Готовые к доставке в SSE. */
  ready: JobSnapshot[];
  lastDelivered: JobSnapshot;
}

/** Канонический снимок JobSnapshot.to_payload() с заменами поверх базы. */
export function snap(version: number, overrides: Partial<JobSnapshot>): JobSnapshot {
  return {
    schema_version: 1,
    version,
    job_id: "job-x",
    kind: "simulate",
    status: "queued",
    stage: "queued",
    series_index: null,
    series_total: null,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

/** Тело SSE-потока с именованными событиями snapshot (routes_jobs.py). */
export function sseBody(events: JobSnapshot[]): string {
  let body = "retry: 150\n\n";
  for (const item of events) {
    body += `event: snapshot\nid: ${item.version}\ndata: ${JSON.stringify(item)}\n\n`;
  }
  return body;
}

export interface JobScript {
  first: JobSnapshot;
  /** Первый рабочий снимок — отдаётся вместе с first автоматически. */
  runningSnap: JobSnapshot | undefined;
  scripted: JobSnapshot[];
}

/** Сценарий успешной задачи: queued → running(i1/N) [→ i2/N] → analyzing → done.
 * Имена записанных сессий индексируются сквозным счётчиком симуляции. */
export function buildJobScript(
  body: Record<string, unknown>,
  jobId: string,
  sessionNumber: number,
): JobScript {
  const kind = String(body.kind) as JobSnapshot["kind"];
  const repeat = Number(body.repeat ?? 1);
  const total = repeat > 1 ? repeat : null;
  const runStage = kind === "capture" ? "capturing" : "simulating";
  const prefix = kind === "capture" ? "cap" : "sim";
  const firstSession = `${prefix}-${String(sessionNumber).padStart(3, "0")}`;
  const sessions: string[] = [firstSession];
  let version = 1;
  const at = (overrides: Partial<JobSnapshot>): JobSnapshot => {
    version += 1;
    return snap(version, { job_id: jobId, kind, ...overrides });
  };
  const scripted: JobSnapshot[] = [
    at({
      status: "running",
      stage: runStage,
      series_index: total === null ? null : 1,
      series_total: total,
    }),
  ];
  if (total !== null) {
    scripted.push(
      at({
        status: "running",
        stage: runStage,
        series_index: 2,
        series_total: total,
        written_sessions: [...sessions],
      }),
    );
  }
  scripted.push(
    at({
      status: "succeeded",
      stage: "analyzing",
      series_index: total,
      series_total: total,
      written_sessions: [...sessions],
    }),
    at({
      status: "succeeded",
      stage: "done",
      series_index: total,
      series_total: total,
      written_sessions: [...sessions],
      result: { sessions },
    }),
  );
  const runningSnap = scripted.shift();
  return { first: snap(1, { job_id: jobId, kind }), runningSnap, scripted };
}

export class JobStore {
  readonly plans = new Map<string, JobPlan>();
  /** Тела запросов POST /api/jobs по порядку поступления. */
  readonly startedRequests: Record<string, unknown>[] = [];
  readonly cancelRequests: string[] = [];
  sessionCounter = 0;
  /** Задача, уже существующая на сервере при монтировании (восстановление). */
  existingJob: JobSnapshot | null = null;

  /** Передаёт следующий сценарный снимок в поток SSE. */
  pump(jobId?: string): void {
    for (const [id, plan] of this.plans) {
      if (jobId !== undefined && id !== jobId) continue;
      const next = plan.scripted.shift();
      if (next !== undefined) plan.ready.push(next);
    }
  }

  /** Передаёт все оставшиеся сценарные снимки сразу. */
  pumpAll(): void {
    for (const plan of this.plans.values()) {
      while (plan.scripted.length > 0) {
        const next = plan.scripted.shift();
        if (next !== undefined) plan.ready.push(next);
      }
    }
  }
}

function startJob(store: JobStore, body: Record<string, unknown>): MockHttpReply {
  store.startedRequests.push(body);
  const jobId = `job-${store.plans.size + 1}`;
  store.sessionCounter += 1;
  const script = buildJobScript(body, jobId, store.sessionCounter);
  // Первый запуск всегда отдаёт queued + первый рабочий снимок автоматически.
  store.plans.set(jobId, {
    scripted: script.scripted,
    ready: script.runningSnap !== undefined ? [script.first, script.runningSnap] : [script.first],
    lastDelivered: script.first,
  });
  return { status: 202, body: script.first };
}

function jobRoute(
  store: JobStore,
  jobId: string,
  suffix: string,
  method: string,
): MockHttpReply | null {
  const plan = store.plans.get(jobId);
  if (suffix === "/events" && method === "GET") {
    if (!plan) {
      return failure(404, { code: "unknown_job", detail: "задача неизвестна" });
    }
    if (plan.ready.length === 0) {
      // События ещё не готовы (ждут pump или отмены).
      return { status: 200, contentType: "text/event-stream", body: "retry: 150\n\n" };
    }
    const pending = [...plan.ready];
    plan.ready.length = 0;
    plan.lastDelivered = pending[pending.length - 1] ?? plan.lastDelivered;
    return { status: 200, contentType: "text/event-stream", body: sseBody(pending) };
  }
  if (suffix === "/cancel" && method === "POST") {
    store.cancelRequests.push(jobId);
    if (!plan) {
      return failure(404, { code: "unknown_job", detail: "задача неизвестна" });
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
    return { status: 202, body: cancelling };
  }
  if (suffix === "" && method === "GET") {
    if (!plan) {
      return failure(404, { code: "unknown_job", detail: "задача неизвестна" });
    }
    return ok(plan.lastDelivered);
  }
  if (suffix === "/history" && method === "GET") {
    return ok({ items: plan ? [plan.lastDelivered] : [] });
  }
  return null;
}

/** Маршруты задач; null — не наш путь. */
export function handleJobs(store: JobStore, request: MockHttpRequest): MockHttpReply | null {
  const { method, path } = request;
  if (path === "/api/jobs" && method === "POST") {
    if (!request.nonceOk) {
      return failure(403, { code: "mutation_nonce_invalid", detail: "nonce недействителен" });
    }
    return startJob(store, request.bodyJson<Record<string, unknown>>());
  }
  const jobMatch = /^\/api\/jobs\/([^/]+)(\/.*)?$/.exec(path);
  if (jobMatch) {
    const handled = jobRoute(store, jobMatch[1] as string, jobMatch[2] ?? "", method);
    if (handled) return handled;
    return notFound(`нет мока: ${method} ${path}`);
  }
  if (path === "/api/jobs" && method === "GET") {
    return ok({ items: store.existingJob ? [store.existingJob] : [] });
  }
  return null;
}

/** Проверка nonce мутаций v2 — единая для jobs/research (пины 403). */
export function requireNonce(request: MockHttpRequest): MockHttpReply | null {
  return request.nonceOk ? null : nonceRejected();
}
