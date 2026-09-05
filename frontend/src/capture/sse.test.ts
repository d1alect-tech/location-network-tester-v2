import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JobSnapshot } from "../api/types-jobs";
import { watchJobEvents } from "./sse";

/** Фальшивый EventSource: эмулирует поток именованных событий "snapshot"
 * (так шлёт routes_jobs.py): подписка через addEventListener. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly snapshotHandlers: Array<(event: { data: string }) => void> = [];

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: { data: string }) => void): void {
    if (type === "snapshot") this.snapshotHandlers.push(handler);
  }

  close(): void {
    this.closed = true;
    this.readyState = 2;
  }

  emit(snapshot: JobSnapshot): void {
    for (const handler of [...this.snapshotHandlers]) {
      handler({ data: JSON.stringify(snapshot) });
    }
  }

  emitRaw(data: string): void {
    for (const handler of [...this.snapshotHandlers]) handler({ data });
  }

  fail(): void {
    this.onerror?.();
  }
}

function snap(overrides: Partial<JobSnapshot> = {}): JobSnapshot {
  return {
    schema_version: 1,
    version: 1,
    job_id: "job-1",
    kind: "capture",
    status: "running",
    stage: "capturing",
    series_index: null,
    series_total: null,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

describe("watchJobEvents (SSE)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function firstSource(): FakeEventSource {
    const source = FakeEventSource.instances[0];
    if (source === undefined) throw new Error("EventSource не создан");
    return source;
  }

  function makeDeps() {
    return {
      eventSourceCtor: FakeEventSource as unknown as typeof EventSource,
      setTimeoutFn: vi.fn((handler: () => void, ms: number) => setTimeout(handler, ms) as unknown),
      clearTimeoutFn: vi.fn((handle: unknown) =>
        clearTimeout(handle as ReturnType<typeof setTimeout>),
      ),
      pollSnapshot: vi.fn(async () => snap({ version: 9 })),
      staleTimeoutMs: 4000,
    };
  }

  it("targets /api/jobs/{id}/events and delivers guarded snapshots", () => {
    const deps = makeDeps();
    const received: JobSnapshot[] = [];
    const handle = watchJobEvents(
      "job-1",
      { onSnapshot: (s) => received.push(s), onConnection: () => {} },
      deps,
    );
    const source = firstSource();
    expect(source.url).toBe("/api/jobs/job-1/events");

    source.emit(snap({ version: 1 }));
    source.emitRaw("not-json");
    source.emitRaw(JSON.stringify({ nope: true }));
    expect(received).toHaveLength(1);
    expect(received[0]?.version).toBe(1);
    handle.close();
  });

  it("uses a named-event listener instead of onmessage", () => {
    const deps = makeDeps();
    const handle = watchJobEvents("job-1", { onSnapshot: () => {}, onConnection: () => {} }, deps);
    const source = firstSource();
    expect(source.onmessage).toBeNull();
    handle.close();
  });

  it("closes the stream when a terminal snapshot arrives", () => {
    const deps = makeDeps();
    const handle = watchJobEvents("job-1", { onSnapshot: () => {}, onConnection: () => {} }, deps);
    const source = firstSource();
    source.emit(snap({ version: 5, status: "succeeded", stage: "done", result: {} }));
    expect(source.closed).toBe(true);
    handle.close();
  });

  it("announces reconnecting on error and polls after stale timeout once", async () => {
    const deps = makeDeps();
    const connections: string[] = [];
    const snapshots: number[] = [];
    const handle = watchJobEvents(
      "job-1",
      {
        onSnapshot: (s) => snapshots.push(s.version),
        onConnection: (kind) => connections.push(kind),
      },
      deps,
    );
    const source = firstSource();
    source.fail();
    expect(connections).toEqual(["reconnecting"]);
    await vi.advanceTimersByTimeAsync(3999);
    expect(deps.pollSnapshot).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(deps.pollSnapshot).toHaveBeenCalledTimes(1);
    // Результат опроса доставляется как обычный снимок.
    expect(snapshots).toContain(9);
    handle.close();
  });

  it("does not schedule a second stale poll while one is pending or after resume", async () => {
    const deps = makeDeps();
    let release!: () => void;
    deps.pollSnapshot = vi.fn(
      () =>
        new Promise<JobSnapshot>((resolve) => {
          release = () => resolve(snap({ version: 8 }));
        }),
    );
    const connections: string[] = [];
    const handle = watchJobEvents(
      "job-1",
      { onSnapshot: () => {}, onConnection: (k) => connections.push(k) },
      deps,
    );
    const source = firstSource();
    source.fail();
    source.fail(); // повторный сбой до опроса не планирует второй таймер
    await vi.advanceTimersByTimeAsync(4000);
    expect(deps.pollSnapshot).toHaveBeenCalledTimes(1);

    // Поток ожил: соединение live, сброс таймера затишья.
    source.onopen?.();
    expect(connections).toEqual(["reconnecting", "live"]);
    release();
    handle.close();
  });

  it("re-announces reconnecting when the stale poll fails", async () => {
    // Given: опрос снимка недоступен (сеть лежит вместе с SSE).
    const deps = makeDeps();
    deps.pollSnapshot = vi.fn(async () => {
      throw new Error("snapshot unavailable");
    });
    const connections: string[] = [];
    const handle = watchJobEvents(
      "job-1",
      { onSnapshot: () => {}, onConnection: (k) => connections.push(k) },
      deps,
    );
    const source = firstSource();

    // When: сбой потока, затем провал fallback-опроса.
    source.fail();
    expect(connections).toEqual(["reconnecting"]);
    await vi.advanceTimersByTimeAsync(4000);

    // Then: деградированное состояние подтверждено повторно — stale-индикатор
    // остаётся видимым, а механизм восстановления — родной реконнект EventSource.
    expect(deps.pollSnapshot).toHaveBeenCalledTimes(1);
    expect(connections).toEqual(["reconnecting", "reconnecting"]);
    handle.close();
  });

  it("close() is idempotent and stops delivery", () => {
    const deps = makeDeps();
    const received: JobSnapshot[] = [];
    const handle = watchJobEvents(
      "job-1",
      { onSnapshot: (s) => received.push(s), onConnection: () => {} },
      deps,
    );
    const source = firstSource();
    handle.close();
    handle.close();
    source.emit(snap({ version: 2 }));
    expect(received).toHaveLength(0);
  });
});
