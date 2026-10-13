/** Контракт live-клиента (routes_live.py): мутации с nonce-заголовком,
 * сужение ответов, SSE-подписка (именнованные события, дедуп объявлений,
 * stale-fallback опрос статуса, идемпотентный close) и stopIfActive. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "./client";
import { createLiveApi } from "./client-live";
import type { LiveStartRequest, LiveTrigger, LiveWatchHandlers } from "./types-live";

const CONFIG = {
  root: "C:\\lnt-sessions-test",
  profiles: [],
  defaults: {
    simulate: { duration_s: 2.4, sample_rate_hz: 20_000_000, seed: 7, repeat: 1, interval_s: 0 },
    capture: { duration_s: 2.4, sample_rate_hz: 20_000_000, range_v: 5, repeat: 1, interval_s: 0 },
    ranges: [5],
  },
  build_id: "test-build",
  mutation_nonce: "test-nonce",
  static_asset_hash: "test-hash",
  static_assets: {},
};

const IDLE = { state: "idle", mode: "sim", busy_reason: null, trigger: null };
const RUNNING = {
  state: "running",
  mode: "sim",
  busy_reason: "устройство занято вкладкой",
  trigger: { level_v: 0, slope: "rising", source: "ch1", mode: "auto", auto_timeout_s: 0.2 },
};

interface Seen {
  posts: Array<{ path: string; body: unknown; nonce: string | undefined }>;
  states: number;
}

function stubFetch(seen: Seen, live: { state: unknown }): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    const headers = (init?.headers ?? {}) as Record<string, string>;
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/live/state")) {
      seen.states += 1;
      return json(live.state);
    }
    if (init?.method === "POST") {
      seen.posts.push({
        path: url,
        body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
        nonce: headers["X-LNT-Mutation-Nonce"],
      });
      if (url.startsWith("/api/live/start")) {
        live.state = RUNNING;
        return json(live.state);
      }
      if (url.startsWith("/api/live/stop")) {
        live.state = IDLE;
        return json(live.state);
      }
      if (url.startsWith("/api/live/config")) return json(live.state);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

const TRIGGER: LiveTrigger = {
  level_v: 0,
  slope: "rising",
  source: "ch1",
  mode: "auto",
  auto_timeout_s: 0.2,
};

const START_REQUEST: LiveStartRequest = {
  sample_rate_hz: 8_000_000,
  ch1_range_v: 5,
  ch1_probe_multiplier: 1,
  trigger: TRIGGER,
};

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

/** Фальшивый EventSource: именованные события + onopen/onerror/close;
 * глобал подменяется через vi.stubGlobal (паттерн settingsWorkspace.test). */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly handlers = new Map<string, Array<(event: { data: string }) => void>>();

  constructor(public readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: { data: string }) => void): void {
    const list = this.handlers.get(type) ?? [];
    list.push(handler);
    this.handlers.set(type, list);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    for (const handler of [...(this.handlers.get(type) ?? [])]) {
      handler({ data: JSON.stringify(data) });
    }
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeEventSource.instances = [];
});

describe("createLiveApi (routes_live.py)", () => {
  it("start/stop/config POST with the launch nonce header and parse the state", async () => {
    const seen: Seen = { posts: [], states: 0 };
    const live = { state: IDLE };
    const api = createLiveApi(new LntApiClient(stubFetch(seen, live)));

    const started = await api.start(START_REQUEST);
    expect(started.state).toBe("running");
    expect(seen.posts[0]).toMatchObject({ path: "/api/live/start", nonce: "test-nonce" });
    expect(seen.posts[0]?.body).toEqual(START_REQUEST);

    await api.updateTrigger(START_REQUEST.trigger);
    expect(seen.posts[1]).toMatchObject({ path: "/api/live/config", nonce: "test-nonce" });

    const stopped = await api.stop();
    expect(stopped.state).toBe("idle");
    expect(seen.posts[2]).toMatchObject({ path: "/api/live/stop", nonce: "test-nonce" });
    expect(seen.posts[2]?.body).toBeUndefined();
  });

  it("state reads the ownership snapshot without a nonce", async () => {
    const seen: Seen = { posts: [], states: 0 };
    const api = createLiveApi(new LntApiClient(stubFetch(seen, { state: RUNNING })));

    const state = await api.state();
    expect(state.mode).toBe("sim");
    expect(state.busy_reason).toContain("занято");
    expect(seen.states).toBe(1);
    expect(seen.posts).toHaveLength(0);
  });

  it("stopIfActive POSTs stop only after a successful start", async () => {
    const seen: Seen = { posts: [], states: 0 };
    const live = { state: IDLE };
    const api = createLiveApi(new LntApiClient(stubFetch(seen, live)));

    await api.stopIfActive();
    expect(seen.posts).toHaveLength(0); // активным поток не считался — POST нет

    await api.start(START_REQUEST);
    await api.stopIfActive();
    const stops = seen.posts.filter((post) => post.path === "/api/live/stop");
    expect(stops).toHaveLength(1);

    await api.stopIfActive(); // после остановки — снова без POST
    expect(seen.posts.filter((post) => post.path === "/api/live/stop")).toHaveLength(1);
  });

  it("watchFrames delivers named events, ignores malformed ones, closes once", async () => {
    const seen: Seen = { posts: [], states: 0 };
    const api = createLiveApi(new LntApiClient(stubFetch(seen, { state: IDLE })));
    const frames: number[] = [];
    const states: string[] = [];
    const connections: string[] = [];
    const handlers: LiveWatchHandlers = {
      onFrame: (frame) => frames.push(frame.frame_index),
      onState: (state) => states.push(state.state),
      onConnection: (kind) => connections.push(kind),
    };

    vi.stubGlobal("EventSource", FakeEventSource);
    const handle = api.watchFrames(handlers);

    const source = FakeEventSource.instances.at(-1);
    expect(source?.url).toBe("/api/live/frames");
    source?.onopen?.();
    source?.emit("frame", {
      frame_index: 3,
      triggered: true,
      emitted_at_s: 0.1,
      dropped_samples: 0,
      skipped_frames: 0,
      sample_rate_hz: 8_000_000,
      frame_samples: 4096,
      decimated: true,
      calibration_used: false,
      ch1: { time_s: [0], voltage_v: [0], point_count: 1 },
      ch2: { time_s: [0], voltage_v: [0], point_count: 1 },
    });
    source?.emit("heartbeat", IDLE);
    source?.emit("frame", "{не-JSON");
    source?.emit("frame", { frame_index: "не-число" });
    await flush();

    expect(frames).toEqual([3]);
    expect(states).toEqual(["idle"]);
    expect(connections).toEqual(["live"]);

    handle.close();
    handle.close(); // идемпотентно
    expect(source?.closed).toBe(true);
  });

  it("watchFrames announces reconnecting on error and stale-polls the state", async () => {
    const seen: Seen = { posts: [], states: 0 };
    const api = createLiveApi(new LntApiClient(stubFetch(seen, { state: RUNNING })));
    const connections: string[] = [];
    const states: string[] = [];
    const timers: Array<() => void> = [];

    vi.stubGlobal("EventSource", FakeEventSource);
    api.watchFrames(
      {
        onFrame: () => undefined,
        onState: (state) => states.push(state.state),
        onConnection: (kind) => connections.push(kind),
      },
      {
        setTimeoutFn: (fn) => {
          timers.push(fn);
          return timers.length;
        },
        clearTimeoutFn: () => undefined,
      },
    );

    const source = FakeEventSource.instances.at(-1);
    source?.onerror?.();
    expect(connections).toEqual(["reconnecting"]);

    // Stale-таймер истёк: fallback-опрос GET /api/live/state приносит снимок.
    timers[0]?.();
    await flush();
    expect(states).toEqual(["running"]);
    expect(seen.states).toBe(1);
  });
});
