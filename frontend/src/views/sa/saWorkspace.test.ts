/** Todo 14: вкладка «Спектроанализатор» — live-контур по контрактам
 * routes_live.py + models_live.py. Покрывается: монтирование скелета
 * (статус прибора, Run/Stop, подписка до старта); Run = старт (если не
 * запущен) + SA-конфиг (POST /api/live/config с триггером-зеркалом и sa);
 * присоединение к ЧУЖОМУ запущенному потоку — НОЛЬ стартов, ровно один
 * SA-конфиг; событие spectrum питает склад и график (рендер-шов) и
 * показания; размонтирование закрывает подписку без остановки —
 * авто-stop остаётся решением AppShell по группе {scope, sa}. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveSpectrumPayload, LiveStatePayload, LiveTrigger } from "../../api/types-live";
import type { ChartHandle, ChartRenderRequest } from "../../components/charts/types";
import { MARKER_WINDOW_OPTIONS } from "../inspect/spectrumSelectors";
import { mountSaWorkspace } from "./saWorkspace";

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

const TRIGGER: LiveTrigger = {
  level_v: 0,
  slope: "rising",
  source: "ch1",
  mode: "auto",
  auto_timeout_s: 0.2,
};

const IDLE: LiveStatePayload = { state: "idle", mode: "sim", busy_reason: null, trigger: null };
const RUNNING: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: "устройство занято вкладкой",
  trigger: TRIGGER,
};

/** Фальшивый EventSource: именованные события frame/spectrum/heartbeat. */
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
    for (const handler of [...(this.handlers.get(type) ?? [])]) {
      handler({ data: JSON.stringify(data) });
    }
  }
}

interface LiveLog {
  starts: Array<{ body: Record<string, unknown>; nonce: string | undefined }>;
  stops: number;
  states: number;
  configs: Array<{ body: Record<string, unknown>; nonce: string | undefined }>;
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
      live.state = { ...RUNNING, state: "stopped", busy_reason: null };
      return json(live.state);
    }
    if (url.startsWith("/api/live/config") && init?.method === "POST") {
      log.configs.push({
        body: JSON.parse(String(init.body)) as Record<string, unknown>,
        nonce: headers["X-LNT-Mutation-Nonce"],
      });
      return json(live.state);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

function sweep(index: number): LiveSpectrumPayload {
  return {
    frame_index: index,
    freq: [1000, 2000, 3000, 4000],
    psd_db: [-60, -40, -30, -50],
    peaks: [{ frequency_hz: 3000, level_db: -30, prominence_db: 30, q_factor: null }],
    meta: { enbw: 75, resolution: 125, window: "hann", rbw: 50 },
  };
}

/** Рендер-шов: перехват запросов графика без uPlot. */
function fakeChartView(): { createView: () => ChartHandle; requests: ChartRenderRequest[] } {
  const requests: ChartRenderRequest[] = [];
  const handle: ChartHandle = {
    root: document.createElement("div"),
    render: (request) => {
      requests.push(request);
    },
    applyTheme: () => undefined,
    getData: () => null,
    destroy: () => undefined,
  };
  return { createView: () => handle, requests };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

const cleanups: Array<() => void> = [];

function mountStub(
  log: LiveLog,
  live: { state: LiveStatePayload },
): {
  container: HTMLElement;
  requests: ChartRenderRequest[];
} {
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(log, live);
  const view = fakeChartView();
  cleanups.push(
    mountSaWorkspace(container, {
      client: new LntApiClient(fetchImpl),
      live: createLiveApi(new LntApiClient(fetchImpl)),
      spectrum: { createView: view.createView },
    }),
  );
  return { container, requests: view.requests };
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("saWorkspace skeleton (Todo 14)", () => {
  it("mounts status panel, Run/Stop, config selectors and opens the stream", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountStub(log, { state: { ...IDLE } });
    await flush();

    const root = container.querySelector(".lnt-sa-workspace");
    expect(root).toBeInstanceOf(HTMLElement);
    expect(root?.getAttribute("role")).toBe("region");
    expect(root?.getAttribute("aria-label")).toBe("Спектроанализатор");
    expect(container.querySelector("h2")?.textContent).toBe("Спектроанализатор");
    expect(container.querySelector(".lnt-sa-device")?.textContent).toContain("Устройство: ready");
    const run = container.querySelector("#lnt-sa-run") as HTMLButtonElement;
    const stop = container.querySelector("#lnt-sa-stop") as HTMLButtonElement;
    expect(run.textContent).toBe("Запустить");
    expect(stop.disabled).toBe(true);
    expect(container.querySelector(".lnt-sa-sim-badge")?.textContent).toBe("Симуляция");
    // Окна — паритет с MARKER_WINDOW_OPTIONS инспекции (пять известных).
    const windowOptions = [...container.querySelectorAll("[data-sa-window] option")].map(
      (node) => (node as HTMLOptionElement).value,
    );
    expect(windowOptions).toEqual([...MARKER_WINDOW_OPTIONS]);
    const detectorOptions = [...container.querySelectorAll("[data-sa-detector] option")].map(
      (node) => (node as HTMLOptionElement).value,
    );
    expect(detectorOptions).toEqual(["mean", "rms", "max-hold", "min-hold"]);
    expect(FakeLiveEventSource.instances).toHaveLength(1);
    expect(log.starts).toHaveLength(0);
  });

  it("Run starts live and configures the SA circuit with the staged config", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountStub(log, { state: { ...IDLE } });
    await flush();

    (container.querySelector("#lnt-sa-run") as HTMLButtonElement).click();
    await flush();

    expect(log.starts).toHaveLength(1);
    expect(log.starts[0]?.nonce).toBe("test-nonce");
    expect(log.configs).toHaveLength(1);
    expect(log.configs[0]?.nonce).toBe("test-nonce");
    const body = log.configs[0]?.body;
    expect(body).toMatchObject({
      level_v: 0,
      slope: "rising",
      source: "ch1",
      mode: "auto",
      sa: {
        rbw_hz: 50,
        window: "hann",
        band_low_hz: 0,
        band_high_hz: 4_000_000,
        detector: "mean",
      },
    });
    expect(container.querySelector(".lnt-sa-state")?.getAttribute("data-live-state")).toBe(
      "running",
    );
    expect((container.querySelector("#lnt-sa-stop") as HTMLButtonElement).disabled).toBe(false);
  });

  it("joins an already-running stream: zero starts, exactly one SA config", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountStub(log, { state: { ...RUNNING } });
    await flush();

    // Присоединение: конфиг SA ушёл ровно один раз, без перезапуска потока.
    expect(log.starts).toHaveLength(0);
    expect(log.configs).toHaveLength(1);
    expect(log.configs[0]?.body).toMatchObject({ sa: { rbw_hz: 50 } });

    // Повторные heartbeat того же захвата не дублируют конфиг.
    FakeLiveEventSource.instances[0]?.emit("heartbeat", RUNNING);
    await flush();
    expect(log.configs).toHaveLength(1);
    expect(container.querySelector(".lnt-sa-state")?.getAttribute("data-live-state")).toBe(
      "running",
    );
  });

  it("spectrum events feed the trace store, the chart and the readout", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container, requests } = mountStub(log, { state: { ...IDLE } });
    await flush();

    FakeLiveEventSource.instances[0]?.emit("spectrum", sweep(3));
    await flush();

    expect(container.querySelector(".lnt-sa-sweep")?.textContent).toBe("3");
    expect(container.querySelector(".lnt-sa-sweeps")?.textContent).toBe("1");
    expect(container.querySelector(".lnt-sa-rbw")?.textContent).toContain("50 Гц");
    expect(container.querySelector(".lnt-sa-peak")?.textContent).toContain("3.0 кГц");
    expect(requests.length).toBeGreaterThan(0);
    const last = requests[requests.length - 1];
    expect(last?.x).toEqual([1000, 2000, 3000, 4000]);
    expect(last?.series[0]?.values).toEqual([-60, -40, -30, -50]);
    expect(last?.yLabel).toContain("дБ");

    // Max-hold тумблер: второй рендер несёт вторую серию (только растущая).
    const maxToggle = container.querySelector('[data-sa-trace="max"]') as HTMLInputElement;
    maxToggle.click();
    await flush();
    FakeLiveEventSource.instances[0]?.emit("spectrum", sweep(4));
    await flush();
    const lastWithHold = requests[requests.length - 1];
    expect(lastWithHold?.series.map((series) => series.label)).toEqual(["Трасса", "Max-hold"]);
  });

  it("unmount closes the SSE stream without stopping live", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    mountStub(log, { state: { ...RUNNING } });
    await flush();
    expect(log.configs).toHaveLength(1);

    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;

    expect(FakeLiveEventSource.instances[0]?.closed).toBe(true);
    expect(log.stops).toBe(0);
  });
});
