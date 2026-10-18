/** Todo 11 RED: послесвечение осциллографа — аккумулятор интенсивности
 * 256 уровней (0..255). Покрывается: нарастание уровня повторными
 * попаданиями с насыщением, затухание до нуля целочисленным шагом,
 * прижимание точек за пределами диапазона к краю сетки, пропуск
 * неконечных значений без исключений.
 * Задача 22 RED (директива GATE A 2026-10-18): режимы времени спада
 * Выкл / ~0,5 с / ~2 с — аналитика: за T секунд яркость падает в 256 раз
 * (фактор кадра = 256^(-dt/T), floor); оверлей ПОВЕРХ uPlot-канваса в
 * фигуре развёртки (НЕ второй рендер-стек, НЕ второй uPlot) — off =
 * аккумулятор пуст; dispose снимает канвас; тумблер в меню захвата;
 * накопление — отображение, НЕ измерение; «аналоговый фосфор» в
 * подписях не обещается. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveStatePayload } from "../../api/types-live";
import {
  PERSISTENCE_GRID_H,
  PERSISTENCE_HIT_LEVEL,
  type PersistenceMode,
  ScopePersistence,
  persistenceDecayFactor,
} from "./scopePersistence";
import { mountScopeStrip } from "./scopeStrip";
import {
  buildPersistenceMenuSection,
  createPersistenceTag,
  mountWavePersistence,
} from "./scopeWavePersistence";
import { mountScopeWorkspace } from "./scopeWorkspace";

describe("ScopePersistence: аккумулятор растёт и насыщается", () => {
  it("повторные попадания в ячейку наращивают уровень, потолок — 255", () => {
    // Given: сетка пуста; точка (t=0, v=0) при диапазоне ±5 В.
    const store = new ScopePersistence();
    expect(store.litCells()).toBe(0);

    // When: один и тот же кадр кладётся трижды без затухания.
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL * 2);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);

    // Then: уровень насыщен на максимуме шкалы и не переливается.
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(255);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(255);
  });

  it("пустой pushChannel (нет точек) не трогает аккумулятор", () => {
    const store = new ScopePersistence();
    store.pushChannel([], [], -5, 5);
    expect(store.litCells()).toBe(0);
  });
});

describe("ScopePersistence: затухание", () => {
  it("шаг затухания ×220/256 понижает уровень и доводит его до нуля", () => {
    // Given: одна точка уровня 96 (t=0 — вырожденная сетка времени, x=0).
    const store = new ScopePersistence();
    store.pushChannel([0], [0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL);

    // When: первый шаг затухания.
    store.decay();

    // Then: 96 × 220 / 256 = 82,5 → 82 (целочисленный пол).
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(82);

    // When: ещё 39 шагов — след гаснет до нуля, не «висит» на единице.
    for (let i = 0; i < 39; i += 1) store.decay();
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(0);
    expect(store.litCells()).toBe(0);
  });

  it("clear гасит аккумулятор целиком", () => {
    const store = new ScopePersistence();
    store.pushChannel([0, 0.001], [1, -1], -5, 5);
    expect(store.litCells()).toBeGreaterThan(0);
    store.clear();
    expect(store.litCells()).toBe(0);
  });
});

describe("ScopePersistence: границы сетки", () => {
  it("вольты за пределами диапазона прижимаются к краю, не бросают исключение", () => {
    const store = new ScopePersistence();
    store.pushChannel([0], [100], -5, 5);
    store.pushChannel([0], [-100], -5, 5);
    expect(store.levelAt(0, 0)).toBe(PERSISTENCE_HIT_LEVEL);
    expect(store.levelAt(0, PERSISTENCE_GRID_H - 1)).toBe(PERSISTENCE_HIT_LEVEL);
  });

  it("неконечные точки пропускаются, конечные рядом — пишутся", () => {
    const store = new ScopePersistence();
    store.pushChannel([0, 0.001], [Number.NaN, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(0);
    expect(store.levelAt(511, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL);
  });

  it("вырожденный диапазон вольт не делит на ноль", () => {
    const store = new ScopePersistence();
    expect(() => store.pushChannel([0], [0], 0, 0)).not.toThrow();
    expect(store.litCells()).toBeGreaterThan(0);
  });
});

describe("ScopePersistence: режимы времени спада (задача 22)", () => {
  it("фактор кадра — экспонента с базой 256: за T секунд яркость падает в 256 раз", () => {
    // short: T = 0.5 с, кадр 1/30 с → 15 шагов до 1/256; long: T = 2 с → 60.
    const short = persistenceDecayFactor("short", 1 / 30);
    const long = persistenceDecayFactor("long", 1 / 30);
    expect(short).toBeGreaterThan(0);
    expect(short).toBeLessThan(1);
    expect(short ** 15).toBeCloseTo(1 / 256, 9);
    expect(long ** 60).toBeCloseTo(1 / 256, 9);
    expect(long).toBeGreaterThan(short);
    // off — мгновенно темно; мусорный dt — номинальный кадр 1/30 с.
    expect(persistenceDecayFactor("off", 1 / 30)).toBe(0);
    expect(persistenceDecayFactor("short", 0) ** 15).toBeCloseTo(1 / 256, 9);
    expect(persistenceDecayFactor("long", Number.NaN) ** 60).toBeCloseTo(1 / 256, 9);
  });

  it("decayByFactor: 0 — темно, 0.5 — целочисленный пол, 1 — без изменения", () => {
    const store = new ScopePersistence();
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(255);

    store.decayByFactor(0.5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(127);
    store.decayByFactor(1);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(127);
    store.decayByFactor(0);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(0);
    expect(store.litCells()).toBe(0);
  });

  it("спад по режиму: за ~0,5 с след гаснет до нуля, монотонно", () => {
    const store = new ScopePersistence();
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    let level = store.levelAt(0, PERSISTENCE_GRID_H / 2);
    expect(level).toBe(PERSISTENCE_HIT_LEVEL);

    const factor = persistenceDecayFactor("short", 1 / 30);
    for (let step = 0; step < 15; step += 1) {
      store.decayByFactor(factor);
      const next = store.levelAt(0, PERSISTENCE_GRID_H / 2);
      // Монотонность: уровень никогда не растёт (пол гасит до нуля
      // раньше 15-го шага — 96 → 66 → 45 → … → 1 → 0).
      expect(next).toBeLessThanOrEqual(level);
      level = next;
    }
    // 96 × 256^(-1) = 0.375 → пол = 0: после 0.5 с следов нет.
    expect(level).toBe(0);
  });

  it("бюджет кадра аккумулятора: затухание + оба канала 1024 сэмплов < 2 мс", () => {
    const store = new ScopePersistence();
    const time = Array.from({ length: 1024 }, (_, i) => i / 48_000_000);
    const volts = Array.from({ length: 1024 }, (_, i) => Math.sin(i / 8));

    const started = performance.now();
    store.decayByFactor(persistenceDecayFactor("short", 1 / 30));
    store.pushChannel(time, volts, -5, 5);
    store.pushChannel(time, volts, -5, 5);
    const elapsedMs = performance.now() - started;

    expect(elapsedMs).toBeLessThan(2);
  });
});

describe("ScopePersistence: оверлей развёртки (задача 22)", () => {
  const dcFrame = {
    time: [0, 0.001, 0.002, 0.003],
    ch1: [1, 1, 1, 1],
    ch2: [-1, -1, -1, -1],
  };

  it("монтируется поверх uPlot-канваса в фигуре; off = аккумулятор пуст", () => {
    const figure = document.createElement("div");
    const chartRoot = document.createElement("div");
    chartRoot.className = "lnt-uplot-root";
    figure.append(chartRoot);

    const overlay = mountWavePersistence(figure);
    const canvas = figure.querySelector("canvas[data-wave-persistence]");
    expect(canvas).toBeInstanceOf(HTMLCanvasElement);
    // Оверлей ПОСЛЕ корня графика в DOM-порядке (красится поверх), aria-hidden.
    expect(
      (canvas?.compareDocumentPosition(chartRoot) ?? 0) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy();

    overlay.setMode("off");
    overlay.accumulate(dcFrame.time, dcFrame.ch1, dcFrame.ch2, -5, 5, 1 / 30);
    expect(overlay.lit()).toBe(0);
    expect(overlay.mode()).toBe("off");
  });

  it("short: кадры копятся, затухание перед попаданием — свежий кадр полный", () => {
    const figure = document.createElement("div");
    const overlay = mountWavePersistence(figure);
    overlay.setMode("short");

    overlay.accumulate(dcFrame.time, dcFrame.ch1, dcFrame.ch2, -5, 5, 1 / 30);
    expect(overlay.lit()).toBeGreaterThan(0);

    // Аналитика порядка (decay → push), один канал (ch2 = NaN — пропуск):
    // кадр 1: 96; кадр 2: 96 × 256^(-1/15) = 66.3 → 66, +96 = 162.
    overlay.clear();
    overlay.accumulate([0], [0], [Number.NaN], -5, 5, 1 / 30);
    expect(overlay.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(96);
    overlay.accumulate([0], [0], [Number.NaN], -5, 5, 1 / 30);
    expect(overlay.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(162);
  });

  it("переключение в off чистит след; clear гасит; destroy снимает канвас", () => {
    const figure = document.createElement("div");
    const overlay = mountWavePersistence(figure);
    overlay.setMode("short");
    overlay.accumulate(dcFrame.time, dcFrame.ch1, dcFrame.ch2, -5, 5, 1 / 30);
    expect(overlay.lit()).toBeGreaterThan(0);

    overlay.setMode("off");
    expect(overlay.lit()).toBe(0);
    expect(
      figure.querySelector("canvas[data-wave-persistence]")?.getAttribute("data-persist-mode"),
    ).toBe("off");

    overlay.setMode("long");
    overlay.accumulate(dcFrame.time, dcFrame.ch1, dcFrame.ch2, -5, 5, 1 / 30);
    overlay.clear();
    expect(overlay.lit()).toBe(0);

    overlay.destroy();
    expect(figure.querySelector("canvas[data-wave-persistence]")).toBeNull();
  });

  it("секция меню: Выкл/~0,5 с/~2 с; накопление — отображение, НЕ «аналоговый фосфор»", () => {
    const picks: PersistenceMode[] = [];
    const section = buildPersistenceMenuSection({
      current: "off",
      onPick: (mode) => picks.push(mode),
    });

    const buttons = [...section.querySelectorAll<HTMLButtonElement>("[data-menu-persist]")];
    expect(buttons.map((b) => b.getAttribute("data-menu-persist"))).toEqual([
      "off",
      "short",
      "long",
    ]);
    expect(section.textContent).toContain("отображение");
    expect(section.textContent).toContain("не измерение");
    expect(section.textContent).not.toContain("аналоговый фосфор");

    buttons.find((b) => b.getAttribute("data-menu-persist") === "long")?.click();
    expect(picks).toEqual(["long"]);
    expect(
      buttons
        .find((b) => b.getAttribute("data-menu-persist") === "long")
        ?.getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("ярлык состояния развёртки: режим + честная подпись, off — скрыт", () => {
    const tag = createPersistenceTag();
    expect(tag.root.hidden).toBe(true);
    expect(tag.root.getAttribute("data-wave-persist")).toBe("off");

    tag.paint("short");
    expect(tag.root.hidden).toBe(false);
    expect(tag.root.getAttribute("data-wave-persist")).toBe("short");
    expect(tag.root.textContent).toContain("~0,5 с");
    expect(tag.root.textContent).toContain("отображение");
    expect(tag.root.textContent).toContain("не измерение");

    tag.paint("long");
    expect(tag.root.textContent).toContain("~2 с");
    tag.paint("off");
    expect(tag.root.hidden).toBe(true);
  });
});

/* ── Интеграция: тумблер в меню захвата → оверлей в фигуре развёртки ─── */

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

const cleanups: Array<() => void> = [];

function mountTab(live: { state: LiveStatePayload }): HTMLElement {
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(live);
  const liveApi = createLiveApi(new LntApiClient(fetchImpl));
  const workspace = mountScopeWorkspace(container, {
    client: new LntApiClient(fetchImpl),
    live: liveApi,
  });
  cleanups.push(() => workspace.dispose());
  cleanups.push(mountScopeStrip(container, { live: liveApi, workspace }));
  return container;
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
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

describe("scopePersistence: интеграция — тумблер в меню захвата (задача 22)", () => {
  it("тумблер в меню включает оверлей в фигуре; ярлык состояния честный", async () => {
    const container = mountTab({ state: { ...IDLE } });
    await flush();

    // До тумблера: канвас оверлея есть (ария-скрыт), режим off.
    const figure = container.querySelector<HTMLElement>(".lnt-scope-figure");
    expect(figure).toBeInstanceOf(HTMLElement);
    expect(figure?.querySelector("canvas[data-wave-persistence]")).toBeInstanceOf(
      HTMLCanvasElement,
    );
    expect(
      figure?.querySelector("canvas[data-wave-persistence]")?.getAttribute("data-persist-mode"),
    ).toBe("off");
    expect(container.querySelector<HTMLElement>("[data-wave-persist]")?.hidden).toBe(true);

    const panel = openMenu(container);
    panel.querySelector<HTMLButtonElement>('[data-menu-persist="short"]')?.click();
    await flush();

    expect(
      figure?.querySelector("canvas[data-wave-persistence]")?.getAttribute("data-persist-mode"),
    ).toBe("short");
    const tag = container.querySelector<HTMLElement>("[data-wave-persist]");
    expect(tag?.hidden).toBe(false);
    expect(tag?.textContent).toContain("~0,5 с");
    expect(tag?.textContent).toContain("не измерение");

    // Локальный контрол: новых live-подписок не появилось.
    const instances = FakeLiveEventSource.instances.length;
    panel.querySelector<HTMLButtonElement>('[data-menu-persist="off"]')?.click();
    await flush();
    expect(
      figure?.querySelector("canvas[data-wave-persistence]")?.getAttribute("data-persist-mode"),
    ).toBe("off");
    expect(FakeLiveEventSource.instances).toHaveLength(instances);
  });

  it("dispose воркспейса снимает оверлей; контракт DOM-чартов цел", async () => {
    const container = mountTab({ state: { ...IDLE } });
    await flush();

    const panel = openMenu(container);
    panel.querySelector<HTMLButtonElement>('[data-menu-persist="long"]')?.click();
    await flush();
    const figure = container.querySelector<HTMLElement>(".lnt-scope-figure");
    expect(figure?.querySelector("canvas[data-wave-persistence]")).toBeInstanceOf(
      HTMLCanvasElement,
    );

    // dispose воркспейса (не полосы): оверлей и канвасы графика сняты.
    const disposeWorkspace = cleanups[0];
    if (disposeWorkspace === undefined) throw new Error("нет dispose воркспейса");
    disposeWorkspace();
    cleanups.shift();
    expect(figure?.querySelector("canvas[data-wave-persistence]")).toBeNull();

    // Контракт фигуры развёртки жив: статус кадра остаётся в DOM секции.
    expect(container.querySelector(".lnt-scope-wave-status")).toBeInstanceOf(HTMLElement);
    expect(container.querySelector("[data-wave-bw]")).toBeInstanceOf(HTMLElement);
  });
});
