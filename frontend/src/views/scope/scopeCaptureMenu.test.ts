/** Задача 21 RED (директива GATE A 2026-10-18): расширенное меню настройки
 * захвата — disclosure-панель по r4-прецеденту stateless-диалога. Кнопка
 * «Меню» в зоне ГОРИЗ полосы (геометрия: линия 1 стабильна на running,
 * линия 2 растёт живыми значениями Δt·ΔV — замер пробы 1280×720), панель —
 * overlay (absolute, высота полосы не растёт). Пины: (1) манифест-респек — кнопка в зоне,
 * набор зон/линий не меняется, панель скрыта до клика; (2) открытие/закрытие
 * stateless — Esc/клик мимо закрывают БЕЗ изменений (значения контролов и
 * staged-реестр не тронуты); (3) каждый пункт меню пишет ТО ЖЕ поле, что и
 * полоса, — через живые слушатели листьев (клик сегментов/опций, change
 * поля уровня), поэтому стейджинг виден маркерами scopeStatus и уходит со
 * следующим Run; (4) снапшот при открытии — меню показывает текущие цели;
 * (5) running: старт-ручки НЕ применяются на ходу (только staged), триггер
 * уходит конфигом (горячая грамматика наследуется); (6) мусор уровня не
 * уходит в живое поле, честная ошибка в меню. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveStatePayload } from "../../api/types-live";
import { mountScopeStrip } from "./scopeStrip";
import { mountScopeWorkspace } from "./scopeWorkspace";

function button(root: ParentNode, selector: string): HTMLButtonElement {
  const node = root.querySelector(selector);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${selector}`);
  return node;
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
  configs: Array<Record<string, unknown>>;
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
      log.configs.push(JSON.parse(String(init.body)) as Record<string, unknown>);
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

/** Открыть меню захвата (клик по кнопке зоны ИЗМЕР). */
function openMenu(container: HTMLElement): HTMLElement {
  const btn = button(container, '[data-action="capture"] button');
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
  window.location.hash = "";
  document.body.replaceChildren();
});

describe("scopeCaptureMenu: манифест-респек и overlay-геометрия DOM", () => {
  it("кнопка «Захват» в зоне ИЗМЕР линии 2; зоны/линии не меняются; панель скрыта", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();

    const btn = container.querySelector<HTMLButtonElement>('[data-action="capture"] button');
    expect(btn?.textContent).toBe("Меню");
    expect(btn?.getAttribute("aria-haspopup")).toBe("dialog");
    expect(btn?.getAttribute("aria-expanded")).toBe("false");
    // Зона ГОРИЗ (линия 1): линия 1 стабильна на running, линия 2 растёт живыми
    // значениями Δt·ΔV (замер пробы) — кнопка не добавляет линию полосы.
    expect(btn?.closest("[data-zone]")?.getAttribute("data-zone")).toBe("horiz");
    // Манифест-респек: набор зон и число линий полосы не изменились.
    const zones = [
      ...new Set(
        [...container.querySelectorAll("[data-zone]")].map((n) => (n as HTMLElement).dataset.zone),
      ),
    ];
    expect(zones).toEqual(["vert", "horiz", "trig", "run", "measure"]);
    expect(container.querySelectorAll("[data-band-line]")).toHaveLength(2);
    // Панель — overlay-потомок группы (absolute CSS), скрыта до открытия.
    const panel = container.querySelector<HTMLElement>(".lnt-live-capture-menu");
    expect(panel).toBeInstanceOf(HTMLElement);
    expect(panel?.getAttribute("role")).toBe("dialog");
    expect(panel?.hidden).toBe(true);
    expect(panel?.closest('[data-action="capture"]')).toBeInstanceOf(HTMLElement);
    // Открытие не плодит новых live-подписок (меню — чистый локальный DOM).
    expect(FakeLiveEventSource.instances).toHaveLength(5);
  });

  it("панель несёт все capture-настройки: В/дел, пробник, частота, триггер, уровень", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    const panel = openMenu(container);

    for (const row of ["vdiv", "probe", "rate", "trigmode", "trigsource", "trigslope", "level"]) {
      expect(panel.querySelector(`[data-menu-row="${row}"]`), `нет ряда ${row}`).toBeInstanceOf(
        HTMLElement,
      );
    }
    // Опции — те же таблицы, что у полосы: В/дел 5/1/0.5, пробник ×1/×10,
    // частота 7 записей, триггер авто/норм/одиночный, CH1/CH2, подъём/спад.
    expect(panel.querySelectorAll('[data-menu-row="vdiv"] [data-menu-value]')).toHaveLength(3);
    expect(panel.querySelectorAll('[data-menu-row="probe"] [data-menu-value]')).toHaveLength(2);
    expect(panel.querySelectorAll('[data-menu-row="rate"] [data-menu-value]')).toHaveLength(7);
    expect(panel.querySelectorAll('[data-menu-row="trigmode"] [data-menu-value]')).toHaveLength(3);
    expect(panel.querySelectorAll('[data-menu-row="trigsource"] [data-menu-value]')).toHaveLength(
      2,
    );
    expect(panel.querySelectorAll('[data-menu-row="trigslope"] [data-menu-value]')).toHaveLength(2);
  });
});

describe("scopeCaptureMenu: stateless-диалог (r4-прецедент)", () => {
  it("клик открывает, Esc закрывает БЕЗ изменений: значения и staged-реестр не тронуты", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();

    const panel = openMenu(container);
    expect(panel.hidden).toBe(false);
    expect(
      container.querySelector('[data-action="capture"] button')?.getAttribute("aria-expanded"),
    ).toBe("true");

    panel.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flush();

    expect(panel.hidden).toBe(true);
    expect(
      container.querySelector('[data-action="capture"] button')?.getAttribute("aria-expanded"),
    ).toBe("false");
    // БЕЗ изменений: сегменты полосы, чип частоты, поле уровня, staged-строка.
    expect(
      container
        .querySelector('#lnt-scope-vdiv button[aria-pressed="true"]')
        ?.getAttribute("data-value"),
    ).toBe("5");
    expect(container.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");
    expect(container.querySelector<HTMLInputElement>("#lnt-scope-level")?.value).toBe("0");
    for (const mark of container.querySelectorAll<HTMLElement>("[data-live-mark]")) {
      expect(mark.hidden, `маркер ${mark.dataset.liveMark} не должен быть виден`).toBe(true);
    }
    expect(container.querySelector<HTMLElement>("[data-staged-line]")?.hidden).toBe(true);
  });

  it("клик мимо закрывает без изменений; кнопка снова открывает", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();

    const panel = openMenu(container);
    document.body.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    expect(panel.hidden).toBe(true);

    openMenu(container);
    expect(panel.hidden).toBe(false);
  });
});

describe("scopeCaptureMenu: каждый пункт пишет то же поле, что и полоса (стадийно)", () => {
  it("В/дел, пробник, частота: staged-маркеры полосы + Run уносит цели в старт", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    const panel = openMenu(container);

    button(panel, '[data-menu-row="vdiv"] [data-menu-value="1"]').click();
    button(panel, '[data-menu-row="probe"] [data-menu-value="10"]').click();
    button(panel, '[data-menu-row="rate"] [data-menu-value="2000000"]').click();
    await flush();

    // Те же поля, что у полосы: реальные сегменты переехали, маркеры зажглись.
    expect(
      container
        .querySelector('#lnt-scope-vdiv button[aria-pressed="true"]')
        ?.getAttribute("data-value"),
    ).toBe("1");
    expect(container.querySelector('[data-live-mark="vdiv"]')?.textContent).toBe("→ 1 В/дел");
    expect(container.querySelector('[data-live-mark="probe"]')?.textContent).toBe("→ ×10");
    expect(container.querySelector('[data-live-mark="rate"]')?.textContent).toBe("→ 2 МГц");
    expect(container.querySelector("[data-staged-line]")?.textContent).toContain(
      "применится при следующем запуске",
    );
    // Слот чипа не врёт: применённая частота остаётся 8 МГц до Run.
    expect(container.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");
    // Выбор НЕ закрывает панель: несколько настроек за одно открытие.
    expect(panel.hidden).toBe(false);

    button(container, "#lnt-scope-run").click();
    await flush();
    expect(log.starts[0]?.body).toMatchObject({
      ch1_range_v: 1,
      ch1_probe_multiplier: 10,
      sample_rate_hz: 2_000_000,
    });
  });

  it("триггер (режим/источник/фронт) и уровень: та же дорога, что у полосы", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    const panel = openMenu(container);

    button(panel, '[data-menu-row="trigmode"] [data-menu-value="normal"]').click();
    button(panel, '[data-menu-row="trigsource"] [data-menu-value="ch2"]').click();
    button(panel, '[data-menu-row="trigslope"] [data-menu-value="falling"]').click();
    await flush();

    // Реальные сегменты триггера нажаты (живая панель, не копия состояния).
    expect(
      container
        .querySelector('button[data-trigger-mode][aria-pressed="true"]')
        ?.getAttribute("data-trigger-mode"),
    ).toBe("normal");
    expect(
      container
        .querySelector('button[data-trigger-source][aria-pressed="true"]')
        ?.getAttribute("data-trigger-source"),
    ).toBe("ch2");
    expect(
      container
        .querySelector('button[data-trigger-slope][aria-pressed="true"]')
        ?.getAttribute("data-trigger-slope"),
    ).toBe("falling");
    expect(container.querySelector('[data-live-mark="trigmode"]')?.textContent).toContain("Норм");
    // Уровень: change поля уровня — живой слушатель, линия триггера синхронна.
    const level = panel.querySelector<HTMLInputElement>("[data-menu-level]");
    if (level === null) throw new Error("нет поля уровня в меню");
    level.value = "1.2";
    level.dispatchEvent(new Event("change", { bubbles: true }));
    await flush();
    expect(container.querySelector<HTMLInputElement>("#lnt-scope-level")?.value).toBe("1.2");
    expect(container.querySelector("[data-trigger-line]")?.getAttribute("aria-valuenow")).toBe(
      "1.2",
    );
    // Idle: триггер стейджится (конфиг не уходит до запуска).
    expect(log.configs).toHaveLength(0);

    button(container, "#lnt-scope-run").click();
    await flush();
    expect(log.starts[0]?.body).toMatchObject({
      trigger: { mode: "normal", source: "ch2", slope: "falling", level_v: 1.2 },
    });
  });

  it("снапшот при открытии: меню показывает текущие цели (staged), не дефолты", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();

    const panel = openMenu(container);
    button(panel, '[data-menu-row="vdiv"] [data-menu-value="1"]').click();
    panel.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flush();

    const reopened = openMenu(container);
    expect(
      reopened
        .querySelector('[data-menu-row="vdiv"] button[aria-pressed="true"]')
        ?.getAttribute("data-menu-value"),
    ).toBe("1");
    expect(reopened.querySelector<HTMLInputElement>("[data-menu-level]")?.value).toBe("0");
  });
});

describe("scopeCaptureMenu: running — старт-ручки только staged, триггер горячий", () => {
  it("на ходу В/дел НЕ применяется (маркер, без POST), триггер уходит конфигом", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const live = { state: { ...IDLE } as LiveStatePayload };
    const container = mountTab(log, live);
    await flush();

    button(container, "#lnt-scope-run").click();
    await flush();
    const panel = openMenu(container);

    button(panel, '[data-menu-row="vdiv"] [data-menu-value="1"]').click();
    await flush();
    // Старт-ручка: только staged-маркер, в прибор ничего не ушло.
    expect(container.querySelector('[data-live-mark="vdiv"]')?.textContent).toBe("→ 1 В/дел");
    expect(log.configs).toHaveLength(0);

    button(panel, '[data-menu-row="trigmode"] [data-menu-value="normal"]').click();
    await flush();
    // Триггер на ходу — горячий: конфиг ушёл (грамматика полосы наследуется).
    expect(log.configs).toHaveLength(1);
    expect(log.configs[0]).toMatchObject({ mode: "normal" });
  });

  it("мусор уровня не уходит в живое поле: честная ошибка в меню", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const live = { state: { ...RUNNING } as LiveStatePayload };
    const container = mountTab(log, live);
    await flush();
    const panel = openMenu(container);

    const level = panel.querySelector<HTMLInputElement>("[data-menu-level]");
    if (level === null) throw new Error("нет поля уровня в меню");
    level.value = "12";
    level.dispatchEvent(new Event("change", { bubbles: true }));
    await flush();

    const error = panel.querySelector<HTMLElement>("[data-menu-level-error]");
    expect(error?.hidden).toBe(false);
    expect(error?.textContent).toContain("от -5 до 5");
    expect(container.querySelector<HTMLInputElement>("#lnt-scope-level")?.value).toBe("0");
    expect(log.configs).toHaveLength(0);
  });
});
