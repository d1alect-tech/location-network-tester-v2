/** Задача 23 RED (директива GATE A 2026-10-18): настройка отображения
 * измерений. Точка сплита названа ДО кода: модуль scopeMeasureConfig.ts
 * ПОГЛОЩАЕТ measure-ряды — buildScopeMeasureSection + ScopeMeasureView
 * переезжают из scopeSections.ts вместе с фильтром видимости; состояние —
 * localStorage lnt.live.meas.v1 (прецедент themePreference). Тумблеры живут
 * РЯДОМ С РИДАУТОМ, НЕ в меню захвата — по геометрии: панель меню
 * открывается вверх и на 1280×625 упирается в бюджет ~450 px (capture-
 * блок уже занимает его), рельс не растёт по высоте (стейдж-доминирование
 * ≥ 60% на 625), поэтому подпись ряда dt СТАНОВИТСЯ тумблером (прецедент
 * компактных чекбоксов рельса: инверсии CH1/CH2 в scopeControls), высота
 * панели не меняется. Пины: (1) тумблер скрывает ряд (dt+dd), другие
 * видны; (2) скрытый ряд = выключен пользователем, НЕ «н/д»: null остаётся
 * «—» у видимых рядов, выключенные просто не рендерятся; (3) состояние
 * переживает перемонт (localStorage); (4) localStorage-контракт: ключ
 * lnt.live.meas.v1, формат «только выключенные», мусор = все включены,
 * неизвестные ключи игнорируются; (5) readout-сетка не ломается: парность
 * dt/dd, applyFrame заполняет значения; (6) тумблер Вкл/Выкл полосы
 * по-прежнему прячет грид целиком (наследие r4); (7) state.set меняет
 * чекбокс (синхронизация состояние → UI). */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveFramePayload, LiveStatePayload } from "../../api/types-live";
import {
  MEASURE_STORAGE_KEY,
  buildScopeMeasureSection,
  createMeasureRowState,
} from "./scopeMeasureConfig";
import { mountScopeStrip } from "./scopeStrip";
import { mountScopeWorkspace } from "./scopeWorkspace";

function button(root: ParentNode, selector: string): HTMLButtonElement {
  const node = root.querySelector(selector);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${selector}`);
  return node;
}

/** Клик по чекбоксу: jsdom не синтезирует change из click — браузер делает;
 * e2e (реальный Chromium) гоняет настоящий путь, здесь посылаем то же
 * событие, что шлёт браузер. */
function toggleBox(input: HTMLInputElement): void {
  input.click();
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

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
      live.state = { ...live.state, state: "running" };
      return json(live.state);
    }
    if (url.startsWith("/api/live/stop") && init?.method === "POST") {
      log.stops += 1;
      return json({ ...live.state, state: "idle" });
    }
    if (url.startsWith("/api/live/config") && init?.method === "POST") {
      log.configs += 1;
      return json(live.state);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
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

/** Кадр-синус 1.25 кГц: аналитическая истина Vpp=3.4 В, VRMS=1.202 В, T=800 мкс. */
function measureFrame(): LiveFramePayload {
  const points = 200;
  const windowS = 0.002;
  return {
    frame_index: 1,
    triggered: true,
    emitted_at_s: 0,
    dropped_samples: 0,
    skipped_frames: 0,
    sample_rate_hz: 8_000_000,
    frame_samples: 4096,
    decimated: true,
    calibration_used: false,
    ch1: {
      time_s: Array.from({ length: points }, (_, i) => (i / points) * windowS),
      voltage_v: Array.from(
        { length: points },
        (_, i) => 1.7 * Math.sin((2 * Math.PI * 2.5 * i) / points),
      ),
      point_count: points,
    },
    ch2: { time_s: [], voltage_v: [], point_count: 0 },
  };
}

function zeroFrame(): LiveFramePayload {
  return {
    ...measureFrame(),
    ch1: {
      time_s: Array.from({ length: 64 }, (_, i) => i * 1e-5),
      voltage_v: Array.from({ length: 64 }, () => 0),
      point_count: 64,
    },
  };
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  window.localStorage.clear();
  window.location.hash = "";
  document.body.replaceChildren();
});

describe("createMeasureRowState: localStorage lnt.live.meas.v1", () => {
  it("по умолчанию все ряды включены; set выключает и пишет хранилище", () => {
    const state = createMeasureRowState();
    for (const key of ["vpp", "vmax", "vmin", "rms", "freq", "period", "duty"]) {
      expect(state.enabled(key as "vpp"), `${key} должен быть включён`).toBe(true);
    }
    expect(window.localStorage.getItem(MEASURE_STORAGE_KEY)).toBeNull();

    state.set("vpp", false);
    state.set("period", false);
    expect(state.enabled("vpp")).toBe(false);
    expect(state.enabled("period")).toBe(false);
    expect(state.enabled("vmax")).toBe(true);
    // Контракт хранения: JSON «только выключенные ряды».
    expect(JSON.parse(window.localStorage.getItem(MEASURE_STORAGE_KEY) ?? "{}")).toEqual({
      vpp: false,
      period: false,
    });
    // Обратное включение убирает ряд из хранилища.
    state.set("period", true);
    expect(JSON.parse(window.localStorage.getItem(MEASURE_STORAGE_KEY) ?? "{}")).toEqual({
      vpp: false,
    });
  });

  it("состояние переживает reset: новый state читает хранилище", () => {
    const first = createMeasureRowState();
    first.set("vpp", false);
    first.set("duty", false);

    const second = createMeasureRowState();
    expect(second.enabled("vpp")).toBe(false);
    expect(second.enabled("duty")).toBe(false);
    expect(second.enabled("vmax")).toBe(true);
  });

  it("мусорный JSON = все включены; неизвестные ключи игнорируются", () => {
    window.localStorage.setItem(MEASURE_STORAGE_KEY, "{не json");
    expect(createMeasureRowState().enabled("vpp")).toBe(true);

    window.localStorage.setItem(MEASURE_STORAGE_KEY, '{"zzz": false, "vpp": false}');
    const state = createMeasureRowState();
    expect(state.enabled("vpp")).toBe(false);
    // Неизвестный ключ не ломает состояние и не попадает в запись.
    state.set("vmax", false);
    expect(JSON.parse(window.localStorage.getItem(MEASURE_STORAGE_KEY) ?? "{}")).toEqual({
      vpp: false,
      vmax: false,
    });
  });
});

describe("buildScopeMeasureSection: тумблеры рядов рядом с ридaутом", () => {
  it("тумблер скрывает ряд (dt+dd не рендерятся), остальные видны", () => {
    const state = createMeasureRowState();
    const view = buildScopeMeasureSection(state);

    // Подпись ряда = тумблер: label.readout-label > checkbox + текст.
    const toggles = view.root.querySelectorAll("[data-measure-toggle]");
    expect(toggles).toHaveLength(7);
    const vppToggle = view.root.querySelector<HTMLInputElement>('[data-measure-toggle="vpp"]');
    if (vppToggle === null) throw new Error("нет тумблера Vpp");

    toggleBox(vppToggle);
    expect(view.root.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);
    // Подпись-тумблер ДОСТУПНА (ряд можно вернуть), скрыто только значение.
    expect(vppToggle.closest("dt")?.hidden).toBe(false);
    // Остальные ряды видны.
    expect(view.root.querySelector<HTMLElement>(".lnt-scope-rms")?.hidden).toBe(false);
    expect(view.root.querySelector<HTMLElement>(".lnt-scope-duty")?.hidden).toBe(false);
    // Хранилище отражает выключение.
    expect(JSON.parse(window.localStorage.getItem(MEASURE_STORAGE_KEY) ?? "{}")).toEqual({
      vpp: false,
    });
  });

  it("state.set синхронизирует чекбокс (состояние → UI)", () => {
    const state = createMeasureRowState();
    state.set("vpp", false);
    const view = buildScopeMeasureSection(state);
    // На сборке: выключенный ряд уже снят и скрыт.
    expect(view.root.querySelector<HTMLInputElement>('[data-measure-toggle="vpp"]')?.checked).toBe(
      false,
    );
    expect(view.root.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);

    // Изменение состояния после сборки: чекбокс и видимость следуют.
    state.set("vpp", true);
    expect(view.root.querySelector<HTMLInputElement>('[data-measure-toggle="vpp"]')?.checked).toBe(
      true,
    );
    expect(view.root.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(false);
  });

  it("скрытый ряд = выключен, НЕ «н/д»: null остаётся «—» у видимых рядов", () => {
    const state = createMeasureRowState();
    const view = buildScopeMeasureSection(state);
    state.set("vpp", false);

    view.applyFrame(zeroFrame(), null);
    // Недоступные значения: видимый ряд честно «—» (unavailable, never fabricated).
    expect(view.root.querySelector(".lnt-scope-rms")?.textContent).toBe("—");
    // Выключенный ряд НЕ рендерится (hidden, не «н/д» в сетке).
    expect(view.root.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);
  });

  it("readout-сетка не ломается: applyFrame заполняет видимые ряды истиной", () => {
    const state = createMeasureRowState();
    const view = buildScopeMeasureSection(state);
    state.set("vpp", false);

    view.applyFrame(measureFrame(), null);
    // Аналитическая истина синуса: VRMS=1.202 В, T=800 мкс — видимые ряды живы.
    expect(view.root.querySelector(".lnt-scope-rms")?.textContent).toBe("1.202 В");
    expect(view.root.querySelector(".lnt-scope-period")?.textContent).toBe("800.000 мкс");
    expect(view.root.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);
    // Парность сетки: 7 пар dt/dd (скрытые в счёте DOM, «не рендерятся»).
    expect(view.root.querySelectorAll(".readout-grid dt")).toHaveLength(7);
    expect(view.root.querySelectorAll(".readout-grid dd")).toHaveLength(7);
  });

  it("тумблер Вкл/Выкл полосы по-прежнему прячет грид целиком (наследие)", () => {
    const state = createMeasureRowState();
    const view = buildScopeMeasureSection(state);
    const grid = view.root.querySelector<HTMLElement>(".readout-grid");
    if (grid === null) throw new Error("нет грида измерений");
    const segOff = view.toggle.querySelector('button[data-value="off"]');
    if (!(segOff instanceof HTMLButtonElement)) throw new Error("нет сегмента Выкл");
    segOff.click();
    expect(grid.hidden).toBe(true);
  });
});

describe("интеграция: ряды рельса + полоса (state переживает перемонт)", () => {
  it("тумблер в рельсе прячет ряд; кадр заполняет видимые ряды", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();

    // Рельс измерений: 7 тумблеров-подписей в гриде.
    const toggles = container.querySelectorAll(".lnt-scope-measure [data-measure-toggle]");
    expect(toggles).toHaveLength(7);
    const vppToggle = container.querySelector<HTMLInputElement>(
      ".lnt-scope-measure [data-measure-toggle='vpp']",
    );
    if (vppToggle === null) throw new Error("нет тумблера Vpp в рельсе");

    expect(container.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(false);
    toggleBox(vppToggle);
    await flush();

    // Ряд скрыт, тумблер снят, хранилище записано, сетка не сломана.
    expect(container.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);
    expect(vppToggle.checked).toBe(false);
    expect(JSON.parse(window.localStorage.getItem(MEASURE_STORAGE_KEY) ?? "{}")).toEqual({
      vpp: false,
    });
    expect(container.querySelectorAll(".lnt-scope-measure .readout-grid dt")).toHaveLength(7);
    expect(container.querySelector<HTMLElement>(".lnt-scope-rms")?.hidden).toBe(false);

    // Кадр приходит: видимые ряды заполняются, скрытый не рендерится.
    FakeLiveEventSource.instances[0]?.emit("frame", measureFrame());
    await flush();
    expect(container.querySelector(".lnt-scope-rms")?.textContent).toBe("1.202 В");
    expect(container.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);
  });

  it("состояние переживает перемонт вкладки: ряд остаётся выключенным", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    const vppToggle = container.querySelector<HTMLInputElement>(
      ".lnt-scope-measure [data-measure-toggle='vpp']",
    );
    if (vppToggle === null) throw new Error("нет тумблера Vpp в рельсе");
    toggleBox(vppToggle);
    await flush();
    expect(container.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);

    // Полный перемонт вкладки (dispose + mount): скрытие пережило reset.
    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;
    document.body.replaceChildren();

    const log2: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container2 = mountTab(log2, { state: { ...IDLE } });
    await flush();
    expect(container2.querySelector<HTMLElement>(".lnt-scope-vpp")?.hidden).toBe(true);
    expect(container2.querySelector<HTMLElement>(".lnt-scope-rms")?.hidden).toBe(false);
    expect(container2.querySelector<HTMLInputElement>("[data-measure-toggle='vpp']")?.checked).toBe(
      false,
    );
  });

  it("меню захвата из задачи 21 не тронуто: без секции измерений", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    button(container, '[data-action="capture"] .lnt-live-capture-btn').click();
    const panel = container.querySelector<HTMLElement>(".lnt-live-capture-menu");
    if (panel === null) throw new Error("нет панели меню захвата");
    expect(panel.hidden).toBe(false);
    // Геометрия меню не изменилась: тумблеры НЕ переехали в оверлей.
    expect(panel.querySelectorAll("[data-measure-toggle]")).toHaveLength(0);
    expect(panel.querySelectorAll("[data-menu-row]")).toHaveLength(7);
  });
});
