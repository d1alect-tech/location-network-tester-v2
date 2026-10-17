/** Задача 8 (D1e/R5): честный прогресс задачи анализа v2 — чистый маппинг
 * снимка задачи в состояние прогресса (переиспользует словарь стадий
 * capture/jobTimeline) и SSE-ожидание терминала поверх capture/sse.ts.
 * Доля НИКОГДА не выдумывается: стадия без серийных данных — indeterminate,
 * не сфабрикованный 0.5 («unavailable, never fabricated»). */

import { describe, expect, it, vi } from "vitest";
import { ApiError, isAbortError } from "../../api/errors";
import type { JobSnapshot, JobStage } from "../../api/types-jobs";
import { jobProgressView, stageLabelOf, watchJobTerminal } from "./w1JobProgress";

function snap(overrides: Partial<JobSnapshot>): JobSnapshot {
  return {
    schema_version: 1,
    version: 1,
    job_id: "job-8",
    kind: "analyze",
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

type FrameListener = (event: MessageEvent<string>) => void;

/** jsdom не реализует EventSource — фальшивый конструктор по контракту sse.ts:
 * именованные события snapshot доставляет emit(), close() помечает поток. */
class FakeEventSource {
  static readonly instances: FakeEventSource[] = [];
  readonly url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly frames = new Set<FrameListener>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: FrameListener): void {
    if (type === "snapshot") this.frames.add(listener);
  }

  close(): void {
    this.closed = true;
  }

  emit(snapshot: JobSnapshot): void {
    const event = new MessageEvent("snapshot", { data: JSON.stringify(snapshot) });
    for (const listener of this.frames) listener(event);
  }
}

const FAKE_CTOR = FakeEventSource as unknown as typeof EventSource;

describe("jobProgressView — честное состояние из снимка", () => {
  it("стадия без серийных данных — indeterminate, НЕ выдуманная доля 0.5", () => {
    const view = jobProgressView(snap({ status: "running", stage: "analyzing" }));
    expect(view).toEqual({ kind: "indeterminate", label: "Стадия: анализ" });
  });

  it("серийная задача даёт реальную долю серии со стадией из словаря", () => {
    const view = jobProgressView(
      snap({ status: "running", stage: "capturing", series_index: 2, series_total: 5 }),
    );
    expect(view).toEqual({ kind: "series", label: "захват", index: 2, total: 5 });
  });

  it("терминал-успех: терминальный вид с меткой статуса", () => {
    expect(jobProgressView(snap({ status: "succeeded", stage: "done" }))).toEqual({
      kind: "terminal",
      label: "Задача завершена",
      succeeded: true,
    });
  });

  it("терминал-провал: статус словаря + серверное сообщение", () => {
    expect(jobProgressView(snap({ status: "failed", error_message: "ветка упала" }))).toEqual({
      kind: "terminal",
      label: "Задача завершилась с ошибкой ветка упала",
      succeeded: false,
    });
  });

  it("незнакомая стадия показывается как есть, не прячется", () => {
    expect(stageLabelOf("mystery" as JobStage)).toBe("mystery");
  });
});

describe("watchJobTerminal — SSE-ожидание поверх capture/sse.ts", () => {
  it("каждый новый снимок уходит в onSnapshot; терминал резолвит ожидание и закрывает поток", async () => {
    FakeEventSource.instances.length = 0;
    const seen: JobSnapshot[] = [];
    const watch = watchJobTerminal(
      snap({ status: "queued", stage: "queued" }),
      (snapshot) => seen.push(snapshot),
      () => Promise.resolve(snap({ version: 2, status: "running", stage: "analyzing" })),
      { eventSourceCtor: FAKE_CTOR, pollIntervalMs: 50 },
    );
    const source = FakeEventSource.instances[0];
    expect(source).toBeDefined();
    expect(source?.url).toBe("/api/jobs/job-8/events");

    source?.emit(snap({ version: 2, status: "running", stage: "analyzing" }));
    source?.emit(snap({ version: 3, status: "succeeded", stage: "done" }));

    await expect(watch.result).resolves.toMatchObject({ version: 3, status: "succeeded" });
    expect(seen.map((item) => item.version)).toEqual([2, 3]);
    expect(source?.closed).toBe(true);
    watch.close();
  });

  it("сервер недоступен: подряд неудачные опросы прерывают ожидание последней ошибкой", async () => {
    FakeEventSource.instances.length = 0;
    const watch = watchJobTerminal(
      snap({ status: "queued" }),
      () => undefined,
      () => Promise.reject(new ApiError("http", { status: 500, detail: "задача недоступна" })),
      { eventSourceCtor: FAKE_CTOR, pollIntervalMs: 1, giveUpAfterPolls: 2 },
    );
    const source = FakeEventSource.instances[0];
    const outcome = watch.result.then(
      () => "resolved",
      (error: unknown) => error,
    );
    await vi.waitFor(() => expect(outcome).resolves.toBeInstanceOf(ApiError));
    const error = (await outcome) as ApiError;
    expect(error.detail).toBe("задача недоступна");
    expect(source?.closed).toBe(true);
  });

  it("close() прерывает ожидание AbortError'ом (teardown вида)", async () => {
    FakeEventSource.instances.length = 0;
    const watch = watchJobTerminal(
      snap({ status: "queued" }),
      () => undefined,
      () => Promise.resolve(snap({ version: 2, status: "running" })),
      { eventSourceCtor: FAKE_CTOR, pollIntervalMs: 50 },
    );
    const outcome = watch.result.then(
      () => "resolved",
      (error: unknown) => error,
    );
    watch.close();
    expect(isAbortError(await outcome)).toBe(true);
  });
});
