/** Задача 24 RED (директива GATE A 2026-10-18): программный ФНЧ полосы
 * пропускания перед отрисовкой — клиентский фильтр кадра (бэкенд не
 * трогается, payload уже несёт сэмплы). Формулы — АНАЛИТИЧЕСКИЕ:
 * (1) окно-ящик длины L = round(fs/cutoff): первый спектральный нуль
 *     лежит на fs/L ≈ cutoff, DC-усиление = 1 (среднее констант);
 * (2) усиление синуса частоты f: |sin(π f L/fs) / (L·sin(π f/fs))|;
 *     для f = 10 МГц, fs = 48 МГц, cutoff 5 МГц (L = 10) ≈ 0.043;
 * (3) для cutoff 1 МГц (L = 48) окно 48 сэмплов = ровно 10 периодов
 *     синуса 10 МГц → сумма окна = 0 точно (спектральный нуль).
 * Прореживание шагом L/2 держит ≥ 2 точек на период среза — без
 * алиасных биений на дисплее. Пины: режимы full/~5 МГц/~1 МГц, входы
 * не мутируются, бюджет кадра 1024 сэмпла < 2 мс. Подпись
 * «программный фильтр, не аналоговый предел» — в меню и в ярлыке
 * состояния развёртки; измерения (Vpp/RMS/частота) — по НЕфильтрованным
 * отсчётам (математика measureSeries не меняется). */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveChannelSeries, LiveFramePayload, LiveStatePayload } from "../../api/types-live";
import type { ChartHandle, ChartRenderRequest } from "../../components/charts/types";
import {
  BW_FILTER_HINT,
  type BwFilterMode,
  buildBwFilterMenuSection,
  filterLiveFrame,
  filterSeries,
} from "./scopeBwFilter";
import { mountScopeStrip } from "./scopeStrip";
import { mountScopeWorkspace } from "./scopeWorkspace";

const FS_HZ = 48_000_000;

function sineSeries(points: number, amplitude: number, freqHz: number): LiveChannelSeries {
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  for (let i = 0; i < points; i += 1) {
    const t = i / FS_HZ;
    time_s.push(t);
    voltage_v.push(amplitude * Math.sin(2 * Math.PI * freqHz * t));
  }
  return { time_s, voltage_v, point_count: points };
}

function dcSeries(points: number, levelV: number): LiveChannelSeries {
  return {
    time_s: Array.from({ length: points }, (_, i) => i / FS_HZ),
    voltage_v: Array.from({ length: points }, () => levelV),
    point_count: points,
  };
}

function liveFrame(ch1: LiveChannelSeries, ch2: LiveChannelSeries): LiveFramePayload {
  return {
    frame_index: 1,
    triggered: true,
    emitted_at_s: 0.1,
    dropped_samples: 0,
    skipped_frames: 0,
    sample_rate_hz: FS_HZ,
    frame_samples: ch1.point_count,
    decimated: false,
    calibration_used: false,
    ch1,
    ch2,
  };
}

describe("scopeBwFilter: аналитика фильтра (задача 24)", () => {
  it("DC не трогается: константа проходит любым режимом без изменений", () => {
    const cutoffs = { "5mhz": 5_000_000, "1mhz": 1_000_000 } as const;
    for (const mode of ["5mhz", "1mhz"] as const) {
      const series = dcSeries(1024, 1.25);
      const out = filterSeries(series.time_s, series.voltage_v, cutoffs[mode]);
      expect(out.voltageV.length, `режим ${mode}: выход не пуст`).toBeGreaterThan(0);
      for (const value of out.voltageV) {
        expect(value, `режим ${mode}: DC-уровень сохранён`).toBe(1.25);
      }
    }
  });

  it("синус 10 МГц при cutoff 5 МГц ослабляется (усиление окна ≈ 0.043)", () => {
    const input = sineSeries(1024, 1, 10_000_000);
    const out = filterSeries(input.time_s, input.voltage_v, 5_000_000);
    const peak = Math.max(...out.voltageV.map(Math.abs));
    // Аналитика: |sin(π·10·10/48)/(10·sin(π·10/48))| ≈ 0.0425; частичные
    // окна в начале отброшены прореживанием (первый выход — полный окна).
    expect(peak).toBeGreaterThan(0);
    expect(peak).toBeLessThan(0.15);
  });

  it("синус 10 МГц при cutoff 1 МГц гасится почти до нуля (окно = 10 периодов)", () => {
    const input = sineSeries(1024, 1, 10_000_000);
    const out = filterSeries(input.time_s, input.voltage_v, 1_000_000);
    const peak = Math.max(...out.voltageV.map(Math.abs), 0);
    // L = 48 сэмплов = ровно 10 периодов синуса 10 МГц при 48 МГц —
    // сумма окна нулевая точно; допуск — только накопление FP-ошибки.
    expect(peak).toBeLessThan(1e-9);
  });

  it("режимы переключаются: full и низкая fs — нет фильтра, ~5/~1 МГц — разные ряды", () => {
    const ch1 = sineSeries(1024, 1, 10_000_000);
    const ch2 = sineSeries(1024, 0.5, 2_000_000);
    const frame = liveFrame(ch1, ch2);

    // full: кадр проходит как есть (тот же объект, ноль работы).
    expect(filterLiveFrame(frame, "full")).toBe(frame);

    // Эффективная fs ряда ниже среза: фильтровать нечего — тот же кадр.
    const slow = liveFrame(
      {
        time_s: Array.from({ length: 32 }, (_, i) => i / 32_000),
        voltage_v: Array.from({ length: 32 }, () => 0),
        point_count: 32,
      },
      {
        time_s: Array.from({ length: 32 }, (_, i) => i / 32_000),
        voltage_v: Array.from({ length: 32 }, () => 0),
        point_count: 32,
      },
    );
    expect(filterLiveFrame(slow, "5mhz")).toBe(slow);

    // ~5 МГц и ~1 МГц дают РАЗНЫЕ длины ряда (L=10 → шаг 5; L=48 → шаг 24).
    const out5 = filterLiveFrame(frame, "5mhz");
    const out1 = filterLiveFrame(frame, "1mhz");
    expect(out5.ch1.voltage_v.length).toBeGreaterThan(out1.ch1.voltage_v.length);
    expect(out5.ch1.voltage_v.length).toBeLessThan(1024);
    expect(out1.ch1.voltage_v.length).toBeLessThan(out5.ch1.voltage_v.length);
    expect(out5.ch1.point_count).toBe(out5.ch1.voltage_v.length);
    expect(out1.ch1.point_count).toBe(out1.ch1.voltage_v.length);
    // Метаданные кадра не переписываются: это фильтр ОТОБРАЖЕНИЯ.
    expect(out5.sample_rate_hz).toBe(FS_HZ);
    expect(out5.frame_samples).toBe(1024);
  });

  it("исходники не мутируются: payload после фильтра байт-в-байт тот же", () => {
    const ch1 = sineSeries(512, 1, 10_000_000);
    const ch2 = sineSeries(512, 0.5, 3_000_000);
    const frame = liveFrame(ch1, ch2);
    const snapCh1 = [...ch1.voltage_v];
    const snapCh2 = [...ch2.voltage_v];

    filterLiveFrame(frame, "1mhz");

    expect(ch1.voltage_v).toEqual(snapCh1);
    expect(ch2.voltage_v).toEqual(snapCh2);
  });

  it("бюджет кадра: 1024 сэмпла фильтруются быстрее 2 мс", () => {
    const ch1 = sineSeries(1024, 1, 10_000_000);
    const ch2 = sineSeries(1024, 0.5, 3_000_000);
    const frame = liveFrame(ch1, ch2);

    const started = performance.now();
    filterLiveFrame(frame, "1mhz");
    const elapsedMs = performance.now() - started;

    // Пин горячего пути: O(n) скользящее окно; запас > 100×.
    expect(elapsedMs).toBeLessThan(2);
  });
});

describe("scopeBwFilter: секция меню (задача 24)", () => {
  it("три опции full/~5 МГц/~1 МГц; клик переключает и вызывает onPick", () => {
    const picks: BwFilterMode[] = [];
    const section = buildBwFilterMenuSection({
      current: "full",
      onPick: (mode) => picks.push(mode),
    });

    const buttons = [...section.querySelectorAll<HTMLButtonElement>("[data-menu-bw]")];
    expect(buttons.map((b) => b.getAttribute("data-menu-bw"))).toEqual(["full", "5mhz", "1mhz"]);
    expect(
      buttons.find((b) => b.getAttribute("data-menu-bw") === "full")?.getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      buttons.find((b) => b.getAttribute("data-menu-bw") === "5mhz")?.getAttribute("aria-pressed"),
    ).toBe("false");

    buttons.find((b) => b.getAttribute("data-menu-bw") === "5mhz")?.click();
    expect(picks).toEqual(["5mhz"]);
    expect(
      buttons.find((b) => b.getAttribute("data-menu-bw") === "5mhz")?.getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      buttons.find((b) => b.getAttribute("data-menu-bw") === "full")?.getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("подпись честности обязательна: «программный фильтр, не аналоговый предел»", () => {
    const section = buildBwFilterMenuSection({ current: "full", onPick: () => undefined });
    expect(section.textContent).toContain(BW_FILTER_HINT);
    expect(section.textContent).toContain("не аналоговый предел");
    // Измерения — по нефильтрованным отсчётам: подпись говорит и это.
    expect(section.textContent).toContain("нефильтрованным");
  });
});

/* ── Интеграция: тумблер в меню захвата → фильтр в рендере развёртки ──── */

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

function liveStubFetch(live: { state: LiveStatePayload }): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/device/state")) return json(DEVICE_READY);
    if (url.startsWith("/api/live/state")) return json(live.state);
    if (url.startsWith("/api/live/start") && init?.method === "POST") {
      live.state = { ...live.state, state: "running" };
      return json(live.state);
    }
    if (url.startsWith("/api/live/stop") && init?.method === "POST") {
      live.state = { ...live.state, state: "idle" };
      return json(live.state);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

/** Пишет рендер-запросы вместо uPlot: серии видны как данные. */
class RecordingChart implements ChartHandle {
  readonly root = document.createElement("div");
  readonly requests: ChartRenderRequest[] = [];

  render(request: ChartRenderRequest): void {
    this.requests.push(request);
  }

  applyTheme(): void {}

  getData(): unknown {
    return null;
  }

  destroy(): void {}
}

const cleanups: Array<() => void> = [];

function mountTab(live: { state: LiveStatePayload }): {
  container: HTMLElement;
  chart: RecordingChart;
} {
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(live);
  const liveApi = createLiveApi(new LntApiClient(fetchImpl));
  const chart = new RecordingChart();
  const workspace = mountScopeWorkspace(container, {
    client: new LntApiClient(fetchImpl),
    live: liveApi,
    waveform: { createView: () => chart },
  });
  cleanups.push(() => workspace.dispose());
  cleanups.push(mountScopeStrip(container, { live: liveApi, workspace }));
  return { container, chart };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

function emitFrame(frame: LiveFramePayload): void {
  for (const source of [...FakeLiveEventSource.instances]) source.emit("frame", frame);
}

function openMenu(container: HTMLElement): HTMLElement {
  const btn = container.querySelector<HTMLButtonElement>('[data-action="capture"] button');
  if (btn === null) throw new Error("нет кнопки меню захвата");
  btn.click();
  const panel = container.querySelector<HTMLElement>(".lnt-live-capture-menu");
  if (panel === null) throw new Error("нет панели меню захвата");
  return panel;
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("scopeBwFilter: интеграция — тумблер в меню захвата (задача 24)", () => {
  it("~5 МГц из меню: кадр фильтруется в рендере, ярлык честности виден", async () => {
    const { container, chart } = mountTab({ state: { ...IDLE } });
    await flush();

    // До тумблера: кадр 1024 сэмпла идёт в рендер как есть.
    const ch1 = sineSeries(1024, 1, 10_000_000);
    const ch2 = sineSeries(1024, 0.5, 3_000_000);
    emitFrame(liveFrame(ch1, ch2));
    await flush();
    expect(chart.requests.at(-1)?.series[0]?.values).toHaveLength(1024);
    const instancesBefore = FakeLiveEventSource.instances.length;

    const panel = openMenu(container);
    panel.querySelector<HTMLButtonElement>('[data-menu-bw="5mhz"]')?.click();
    await flush();

    // Следующий кадр уже прорежен и ослаблен (L = 10, шаг 5).
    emitFrame(liveFrame(ch1, ch2));
    await flush();
    const request = chart.requests.at(-1);
    const rendered = request?.series[0]?.values ?? [];
    expect(rendered.length).toBeGreaterThan(0);
    expect(rendered.length).toBeLessThan(900);
    expect(Math.max(...rendered.map(Math.abs))).toBeLessThan(0.15);

    // Ярлык состояния развёртки: режим + обязательная подпись честности.
    const tag = container.querySelector<HTMLElement>("[data-wave-bw]");
    expect(tag?.hidden).toBe(false);
    expect(tag?.getAttribute("data-wave-bw")).toBe("5mhz");
    expect(tag?.textContent).toContain("~5 МГц");
    expect(tag?.textContent).toContain("не аналоговый предел");

    // Измерения — по НЕфильтрованным отсчётам: Vpp синуса 1 В ≈ 2 В.
    const vppCell = container.querySelector<HTMLElement>(".lnt-scope-vpp");
    expect(vppCell?.textContent).toContain("В");
    const vpp = Number.parseFloat(vppCell?.textContent ?? "");
    expect(vpp).toBeGreaterThan(1.5);
    expect(vpp).toBeLessThan(2.5);

    // Меню — локальный DOM: новых live-подписок не появилось.
    expect(FakeLiveEventSource.instances).toHaveLength(instancesBefore);
  });

  it("возврат в «Полная»: ярлык гаснет, кадр снова идёт целиком", async () => {
    const { container, chart } = mountTab({ state: { ...IDLE } });
    await flush();

    const panel = openMenu(container);
    panel.querySelector<HTMLButtonElement>('[data-menu-bw="1mhz"]')?.click();
    await flush();
    const ch1 = sineSeries(1024, 1, 10_000_000);
    const ch2 = sineSeries(1024, 0.5, 3_000_000);
    emitFrame(liveFrame(ch1, ch2));
    await flush();
    expect(chart.requests.at(-1)?.series[0]?.values ?? []).toHaveLength(
      Math.ceil((1024 - 47) / 24) + 1,
    );

    panel.querySelector<HTMLButtonElement>('[data-menu-bw="full"]')?.click();
    await flush();
    emitFrame(liveFrame(ch1, ch2));
    await flush();

    expect(chart.requests.at(-1)?.series[0]?.values).toHaveLength(1024);
    const tag = container.querySelector<HTMLElement>("[data-wave-bw]");
    expect(tag?.hidden).toBe(true);
    expect(tag?.getAttribute("data-wave-bw")).toBe("full");
  });
});
