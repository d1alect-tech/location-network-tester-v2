/** r4-final f2: автосет при сигнале больше ЛЮБОГО диапазона честно берёт
 * самый широкий В/дел (наибольший halfSpanVolts), а не первый элемент
 * VDIV_STEPS — фолбэк не должен зависеть от порядка списка. Список
 * переворачивается моком scopeScale: [0] в перевёрнутом списке — самый
 * УЗКИЙ диапазон, ровно та ловушка, которую находил аудит. Монтаж — как в
 * scopeAutoset.test.ts (воркспейс + полоса, живые слушатели DOM). */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveFramePayload, LiveStatePayload } from "../../api/types-live";
import { mountScopeStrip } from "./scopeStrip";
import { mountScopeWorkspace } from "./scopeWorkspace";

vi.mock("./scopeScale", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./scopeScale")>()),
  // Перевёрнутый порядок: фолбэк «сигнал слишком велик» обязан находить
  // самый широкий диапазон сам, а не надеяться на порядок списка.
  VDIV_STEPS: [0.5, 1, 5],
}));

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

const DEVICE_READY = {
  state: "ready",
  description_ru: "Устройство готово к захвату.",
  recovery_action_ru: "Дополнительные действия не требуются.",
};

const IDLE: LiveStatePayload = { state: "idle", mode: "sim", busy_reason: null, trigger: null };
const RUNNING: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: null,
};

class FakeLiveEventSource {
  static instances: FakeLiveEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly handlers = new Map<string, Array<(event: { data: string }) => void>>();

  constructor(public readonly url: string) {
    FakeLiveEventSource.instances.push(this);
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
    if (this.closed) return;
    for (const handler of [...(this.handlers.get(type) ?? [])]) {
      handler({ data: JSON.stringify(data) });
    }
  }
}

interface LiveLog {
  starts: Array<{ body: Record<string, unknown>; nonce: string | undefined }>;
  stops: number;
  states: number;
  configs: number;
}

function liveStubFetch(log: LiveLog, live: { state: LiveStatePayload }): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    const headers = (init?.headers ?? {}) as Record<string, string>;
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/device/state")) return json(DEVICE_READY);
    if (url.startsWith("/api/live/state")) {
      log.states += 1;
      return json(live.state);
    }
    if (url.startsWith("/api/live/start") && init?.method === "POST") {
      log.starts.push({
        body: JSON.parse(String(init.body)) as Record<string, unknown>,
        nonce: headers["X-LNT-Mutation-Nonce"],
      });
      live.state = RUNNING;
      return json(live.state);
    }
    if (url.startsWith("/api/live/stop") && init?.method === "POST") {
      log.stops += 1;
      live.state = IDLE;
      return json(live.state);
    }
    if (url.startsWith("/api/live/config") && init?.method === "POST") {
      log.configs += 1;
      return json(live.state);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

/** Синус 1250 Гц заданной амплитуды, 200 точек в окне 2 мс. */
function frame(amplitude: number): LiveFramePayload {
  const points = 200;
  const windowS = 0.002;
  const ch1 = { time_s: [] as number[], voltage_v: [] as number[], point_count: points };
  for (let i = 0; i < points; i += 1) {
    ch1.time_s.push((i / (points - 1)) * windowS);
    ch1.voltage_v.push(amplitude * Math.sin((2 * Math.PI * 2.5 * i) / (points - 1)));
  }
  return {
    frame_index: 1,
    triggered: true,
    emitted_at_s: 0,
    dropped_samples: 0,
    skipped_frames: 0,
    sample_rate_hz: 8_000_000,
    frame_samples: 2400,
    decimated: true,
    calibration_used: false,
    ch1,
    ch2: { time_s: [] as number[], voltage_v: [] as number[], point_count: 0 },
  };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

function emitAll(type: string, data: unknown): void {
  for (const source of [...FakeLiveEventSource.instances]) source.emit(type, data);
}

const cleanups: Array<() => void> = [];

function mountTab(log: LiveLog, live: { state: LiveStatePayload }): HTMLElement {
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(log, live);
  const liveApi = createLiveApi(new LntApiClient(fetchImpl));
  const workspace = mountScopeWorkspace(container, {
    client: new LntApiClient(fetchImpl),
    live: liveApi,
  });
  cleanups.push(() => workspace.dispose());
  cleanups.push(mountScopeStrip(container, { live: liveApi, workspace }));
  return container;
}

function button(root: ParentNode, selector: string): HTMLButtonElement {
  const node = root.querySelector(selector);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${selector}`);
  return node;
}

function echoOf(root: ParentNode): HTMLElement {
  const node = root.querySelector<HTMLElement>('[data-echo="autoset"]');
  if (node === null) throw new Error("нет эха автосета");
  return node;
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("scopeAutoset: фолбэк «сигнал слишком велик» (r4-final f2)", () => {
  it("пик 45 В не влезает ни в одно окно: автосет берёт 5 В/дел", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    emitAll("frame", frame(45));
    await flush();

    button(container, '[data-action="autoset"] button').click();
    await flush();

    // Самое широкое окно — 5 В/дел (±20 В), не [0] списка.
    expect(log.starts[0]?.body).toMatchObject({ ch1_range_v: 5 });
    expect(echoOf(container).textContent).toContain("В/дел 5");
    expect(echoOf(container).textContent).toContain("частота 1 МГц");
  });

  it("обычный кадр 1,7 В: подбор по-прежнему точен, фолбэк не мешает", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    emitAll("frame", frame(1.7));
    await flush();

    button(container, '[data-action="autoset"] button').click();
    await flush();

    expect(log.starts[0]?.body).toMatchObject({ ch1_range_v: 5 });
    expect(echoOf(container).textContent).toBe("Автонастройка: частота 1 МГц");
  });
});
