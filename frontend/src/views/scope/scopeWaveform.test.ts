/** Todo 8 RED: живая развёртка осциллографа — кадры обоих каналов через
 * общий uPlot-стек (createUplotView + decimateMinMax, без второго стека),
 * V/div из общей таблицы каналов, инверсия каналов, пробник × подписи
 * readout, стабильная сетка между кадрами, NaN/клип с индикацией.
 * Хэндл графика подменяется фальшивым (паттерн spectralOverlay):
 * ассерты идут по рендер-запросам и DOM статусов. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveChannelSeries, LiveFramePayload, LiveStatePayload } from "../../api/types-live";
import type { ChartHandle, ChartRenderRequest } from "../../components/charts/types";
import { DEFAULT_SCOPE_SETTINGS } from "./scopeScale";
import { mountScopeWaveform } from "./scopeWaveform";
import type { ScopeWaveformHandle } from "./scopeWaveform";
import { mountScopeWorkspace } from "./scopeWorkspace";

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

/** Фальшивый EventSource: именованные события frame/heartbeat, как routes_live.py. */
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
      live.state = { ...live.state, state: "running" };
      return json(live.state);
    }
    if (url.startsWith("/api/live/stop") && init?.method === "POST") {
      log.stops += 1;
      live.state = { ...live.state, state: "stopped" };
      return json(live.state);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

function series(points: number, amplitude: number, phase = 0): LiveChannelSeries {
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  for (let i = 0; i < points; i += 1) {
    time_s.push((i / points) * 0.001);
    voltage_v.push(amplitude * Math.sin((i / points) * Math.PI * 2 + phase));
  }
  return { time_s, voltage_v, point_count: points };
}

function frame(
  index: number,
  ch1: LiveChannelSeries = series(32, 1),
  ch2: LiveChannelSeries = series(32, 0.5, Math.PI / 2),
): LiveFramePayload {
  return {
    frame_index: index,
    triggered: true,
    emitted_at_s: index / 30,
    dropped_samples: 0,
    skipped_frames: 0,
    sample_rate_hz: 8_000_000,
    frame_samples: 4096,
    decimated: true,
    calibration_used: false,
    ch1,
    ch2,
  };
}

/** Пишет рендер-запросы вместо uPlot: сетка и серии видны как данные. */
class RecordingChart implements ChartHandle {
  readonly root = document.createElement("div");
  readonly requests: ChartRenderRequest[] = [];
  destroyed = false;

  render(request: ChartRenderRequest): void {
    this.requests.push(request);
  }

  applyTheme(): void {}

  getData(): unknown {
    return null;
  }

  destroy(): void {
    this.destroyed = true;
  }
}

const position = (value: number, min: number, max: number): number => (value - min) / (max - min);

function mountWave(): { wave: ScopeWaveformHandle; chart: RecordingChart } {
  const chart = new RecordingChart();
  const wave = mountScopeWaveform({ createView: () => chart });
  return { wave, chart };
}

const cleanups: Array<() => void> = [];

function mountWorkspace(): { container: HTMLElement; chart: RecordingChart; log: LiveLog } {
  const log: LiveLog = { starts: [], stops: 0, states: 0 };
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const chart = new RecordingChart();
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(log, { state: { ...IDLE } });
  cleanups.push(
    mountScopeWorkspace(container, {
      client: new LntApiClient(fetchImpl),
      live: createLiveApi(new LntApiClient(fetchImpl)),
      waveform: { createView: () => chart },
    }),
  );
  return { container, chart, log };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

function changeSelect(container: HTMLElement, selector: string, value: string): void {
  const select = container.querySelector(selector) as HTMLSelectElement;
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("scopeWaveform rendering (Todo 8)", () => {
  it("draws both channels with distinct token colors and non-color markers", () => {
    const { wave, chart } = mountWave();
    wave.applyFrame(frame(1), { ...DEFAULT_SCOPE_SETTINGS });

    const request = chart.requests.at(-1);
    expect(request?.series).toHaveLength(2);
    expect(request?.series[0]?.label).toBe("CH1");
    expect(request?.series[1]?.label).toBe("CH2");
    expect(request?.series[0]?.color).not.toBe("");
    expect(request?.series[0]?.color).not.toBe(request?.series[1]?.color);
    // Различие не только цветом (DESIGN.md): пунктир и маркер у CH2.
    expect(request?.series[1]?.dash).toBeDefined();
    expect(request?.series[0]?.marker).toBeDefined();
    expect(request?.series[1]?.marker).toBeDefined();
  });

  it("V/div fixes the grid window per the scale law — grid positions", () => {
    const cases: ReadonlyArray<readonly [number, number]> = [
      [5, 5.12],
      [1, 1.024],
      [0.5, 0.512],
    ];
    for (const [vDiv, half] of cases) {
      const { wave, chart } = mountWave();
      wave.applyFrame(frame(1), { ...DEFAULT_SCOPE_SETTINGS, vDiv });
      const request = chart.requests.at(-1);
      const [min, max] = request?.yRange ?? [Number.NaN, Number.NaN];
      expect(position(half, min, max)).toBeCloseTo(1, 9);
      expect(position(0, min, max)).toBeCloseTo(0.5, 9);
      expect(position(-half, min, max)).toBeCloseTo(0, 9);
      expect(request?.xRange?.[0]).toBe(0);
      expect(request?.xRange?.[1]).toBeGreaterThan(0);
    }
  });

  it("inversion flips the sign of its channel only; source stays intact", () => {
    const f = frame(1);
    const originalCh2 = [...f.ch2.voltage_v];
    const { wave, chart } = mountWave();

    wave.applyFrame(f, { ...DEFAULT_SCOPE_SETTINGS, invertCh2: true });

    const request = chart.requests.at(-1);
    expect(request?.series[1]?.values).toEqual(originalCh2.map((value) => -value));
    expect(request?.series[0]?.values).toEqual(f.ch1.voltage_v);
    expect(f.ch2.voltage_v).toEqual(originalCh2);
  });

  it("probe ×10 scales the window together with the readout law", () => {
    const { wave, chart } = mountWave();
    wave.applyFrame(frame(1), { ...DEFAULT_SCOPE_SETTINGS, probe: 10 });
    const [min, max] = chart.requests.at(-1)?.yRange ?? [Number.NaN, Number.NaN];
    expect(max).toBeCloseTo(51.2, 9);
    expect(min).toBeCloseTo(-51.2, 9);
  });

  it("grid is stable between frames and moves only with V/div", () => {
    const { wave, chart } = mountWave();
    wave.applyFrame(frame(1, series(32, 0.4)), { ...DEFAULT_SCOPE_SETTINGS });
    wave.applyFrame(frame(2, series(32, 3.1)), { ...DEFAULT_SCOPE_SETTINGS });

    const first = chart.requests[0];
    const second = chart.requests[1];
    expect(second?.yRange).toEqual(first?.yRange);
    expect(second?.xRange).toEqual(first?.xRange);

    wave.applyFrame(frame(3, series(32, 3.1)), { ...DEFAULT_SCOPE_SETTINGS, vDiv: 1 });
    const third = chart.requests[2];
    expect(third?.yRange).not.toEqual(second?.yRange);
    expect(third?.xRange).toEqual(second?.xRange);
  });

  it("NaN frame: no crash, non-finite dropped and indicated", () => {
    const f = frame(1);
    f.ch1.voltage_v[2] = Number.NaN;
    f.ch2.voltage_v[5] = Number.NaN;
    const { wave, chart } = mountWave();

    expect(() => wave.applyFrame(f, { ...DEFAULT_SCOPE_SETTINGS })).not.toThrow();

    const request = chart.requests.at(-1);
    expect(request?.series[0]?.values.every(Number.isFinite)).toBe(true);
    expect(request?.series[1]?.values.every(Number.isFinite)).toBe(true);
    const status = wave.root.querySelector(".lnt-scope-wave-status") as HTMLElement;
    expect(status).toBeInstanceOf(HTMLElement);
    expect(status.hidden).toBe(false);
    expect(status.textContent).toContain("нечислов");

    // Чистый кадр снимает индикацию.
    wave.applyFrame(frame(2), { ...DEFAULT_SCOPE_SETTINGS });
    const cleared = wave.root.querySelector(".lnt-scope-wave-status") as HTMLElement;
    expect(cleared.hidden).toBe(true);
  });

  it("clip beyond the grid window is indicated, not silent", () => {
    const { wave } = mountWave();
    wave.applyFrame(frame(1, series(32, 1), series(32, 9)), { ...DEFAULT_SCOPE_SETTINGS });
    const status = wave.root.querySelector(".lnt-scope-wave-status") as HTMLElement;
    expect(status.hidden).toBe(false);
    expect(status.textContent).toContain("вне сетки");
  });
});

describe("scopeWorkspace wiring (Todo 8)", () => {
  it("Run sends the selected V/div and probe in POST /api/live/start", async () => {
    const { container, log } = mountWorkspace();
    await flush();

    changeSelect(container, "#lnt-scope-vdiv", "1");
    changeSelect(container, "#lnt-scope-probe", "10");
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();

    expect(log.starts).toHaveLength(1);
    expect(log.starts[0]?.body).toMatchObject({ ch1_range_v: 1, ch1_probe_multiplier: 10 });
  });

  it("probe 1×/10× scales the effective V/div readout label", async () => {
    const { container } = mountWorkspace();
    await flush();

    const label = container.querySelector(".lnt-scope-vdiv-effective");
    expect(label?.textContent).toContain("5 В/дел");

    changeSelect(container, "#lnt-scope-probe", "10");
    await flush();
    expect(label?.textContent).toContain("50 В/дел");
  });

  it("SSE frames reach the chart; a V/div change re-renders the last frame", async () => {
    const { container, chart } = mountWorkspace();
    await flush();

    FakeLiveEventSource.instances[0]?.emit("frame", frame(7));
    await flush();
    expect(chart.requests).toHaveLength(1);
    const before = chart.requests[0]?.yRange;

    changeSelect(container, "#lnt-scope-vdiv", "0.5");
    await flush();
    expect(chart.requests).toHaveLength(2);
    expect(chart.requests[1]?.yRange).not.toEqual(before);
  });
});
