/** Задача 14 RED: композиция scope-вкладки — полоса liveStrip поверх
 * НЕИЗМЕННОГО mountScopeWorkspace (ре-парент живых узлов, слушатели живы):
 * зоны из scope-манифеста; run-контрол отражает live-источник (running →
 * «СТОП»); staged-сценарий «изменил В/дел → маркировка → Run → применилось,
 * маркировка снята»; негативный: staged-число частоты НЕ в слоте текущего
 * значения; dispose закрывает все live-подписки вкладки.
 * Задача 15: линия триггера на экране, автосет/сброс/курсоры в ИЗМЕР,
 * 409-клетка (сигнал конфликта + баннер с переходом). */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveStatePayload } from "../../api/types-live";
import {
  LIVE_ALREADY_RUNNING_RU,
  createLiveConflictSignal,
  signalLiveConflicts,
} from "../../components/liveStrip/liveConflict";
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
    // Как настоящий EventSource: после close() доставка событий мертва.
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

function liveStubFetch(
  log: LiveLog,
  live: { state: LiveStatePayload; start409?: boolean },
): typeof fetch {
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
      if (live.start409 === true) {
        // Живой захват уже идёт на другой вкладке: сервер отдаёт 409.
        return json({ detail: LIVE_ALREADY_RUNNING_RU }, 409);
      }
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

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

function emitAll(type: string, data: unknown): void {
  for (const source of [...FakeLiveEventSource.instances]) source.emit(type, data);
}

const cleanups: Array<() => void> = [];

function mountTab(
  log: LiveLog,
  live: { state: LiveStatePayload; start409?: boolean },
): {
  container: HTMLElement;
  conflict: ReturnType<typeof createLiveConflictSignal>;
} {
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(log, live);
  // Проводка AppShell (задача 15): инструментированный live-контур — 409
  // старта уходит сигналом liveConflict, а не правкой воркспейса.
  const conflict = createLiveConflictSignal();
  const liveApi = signalLiveConflicts(createLiveApi(new LntApiClient(fetchImpl)), conflict);
  cleanups.push(
    mountScopeWorkspace(container, { client: new LntApiClient(fetchImpl), live: liveApi }),
  );
  cleanups.push(mountScopeStrip(container, { live: liveApi, conflictSignal: conflict }));
  return { container, conflict };
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  window.location.hash = "";
  document.body.replaceChildren();
});

describe("scopeStrip: полоса поверх воркспейса (задача 14)", () => {
  it("полоса рендерит зоны из scope-манифеста и ре-парентит живые узлы", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    // Зоны из манифеста: ВЕРТ/ГОРИЗ/ТРИГГ/ЗАПУСК/ИЗМЕР, две линии виджетов.
    const zones = [
      ...new Set(
        [...container.querySelectorAll("[data-zone]")].map((n) => (n as HTMLElement).dataset.zone),
      ),
    ];
    expect(zones).toEqual(["vert", "horiz", "trig", "run", "measure"]);
    const line1 = container.querySelector('[data-band-line="1"]');
    const line2 = container.querySelector('[data-band-line="2"]');
    expect(line1?.querySelector('[data-zone="vert"]')).toBeInstanceOf(HTMLElement);
    expect(line2?.querySelector('[data-zone="measure"]')).toBeInstanceOf(HTMLElement);
    // ТРИГГ продолжается в линию 2: уровень и индикатор тайминга.
    const trigLine2 = line2?.querySelector('[data-zone="trig"]');
    expect(trigLine2?.querySelector("#lnt-scope-level")).toBeInstanceOf(HTMLInputElement);
    expect(trigLine2?.querySelector("[data-trig-state]")).toBeInstanceOf(HTMLElement);
    // Ре-парент живых узлов: кнопки пуска в зоне ЗАПУСК, сегменты В/дел в ВЕРТ.
    expect(
      container.querySelector('[data-zone="run"]')?.querySelector("#lnt-scope-run"),
    ).toBeInstanceOf(HTMLButtonElement);
    expect(
      container.querySelector('[data-zone="vert"]')?.querySelector("#lnt-scope-vdiv"),
    ).toBeInstanceOf(HTMLElement);
    expect(
      container.querySelector('[data-zone="horiz"]')?.querySelector(".lnt-scope-rate-field"),
    ).toBeInstanceOf(HTMLElement);
    // Воркспейс помечен режимом полосы (компактный leftover).
    expect(
      container.querySelector(".lnt-scope-workspace")?.classList.contains("lnt-scope-strip-mode"),
    ).toBe(true);
    // Подписки вкладки: воркспейс + статус + run-кластер + автосет +
    // линия триггера (собственная подписка истины сервиса).
    expect(FakeLiveEventSource.instances).toHaveLength(5);
  });

  it("run-контрол отражает live-источник: running → «СТОП» в паре; dispose отписывается", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    const run = container.querySelector<HTMLButtonElement>("#lnt-scope-run");
    const stop = container.querySelector<HTMLButtonElement>("#lnt-scope-stop");
    expect(run?.textContent).toContain("ЗАПУСК");
    expect(stop?.textContent).toContain("СТОП");
    expect(stop?.getAttribute("aria-checked")).toBe("true");

    run?.click();
    await flush();
    emitAll("heartbeat", RUNNING);
    await flush();

    expect(stop?.getAttribute("aria-checked")).toBe("false");
    expect(run?.getAttribute("aria-checked")).toBe("true");
    // Полоса не владеет run-состоянием: доступность кнопок — работа воркспейса.
    expect(run?.disabled).toBe(true);

    // Dispose: все live-подписки вкладки закрыты, мертвы.
    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;
    expect(FakeLiveEventSource.instances.every((source) => source.closed)).toBe(true);
    emitAll("heartbeat", RUNNING);
    expect(run?.getAttribute("aria-checked")).toBe("true"); // покраска не изменилась
  });

  it("staged-сценарий: изменил В/дел → маркировка → Run → применилось, маркировка снята", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    // When: оператор жмёт сегмент «1» без запуска.
    button(container, '#lnt-scope-vdiv [data-value="1"]').click();
    await flush();

    // Then: маркировка staged — маркер, строка, бейдж; слот не врёт.
    const mark = container.querySelector<HTMLElement>('[data-live-mark="vdiv"]');
    expect(mark?.hidden).toBe(false);
    expect(mark?.textContent).toBe("→ 1 В/дел");
    expect(container.querySelector("[data-staged-line]")?.textContent).toContain(
      "применится при следующем запуске",
    );
    const badge = container.querySelector<HTMLElement>(".lnt-live-runbadge");
    expect(badge?.hidden).toBe(false);
    expect(badge?.textContent).toContain("отложено к запуску");

    // When: запуск применяет staged.
    button(container, "#lnt-scope-run").click();
    await flush();
    expect(log.starts[0]?.body).toMatchObject({ ch1_range_v: 1 });
    emitAll("heartbeat", RUNNING);
    await flush();

    // Then: маркировка снята — маркеры погашены, бейдж скрыт, строка пуста.
    expect(mark?.hidden).toBe(true);
    expect(badge?.hidden).toBe(true);
    expect(container.querySelector("[data-staged-line]")?.textContent).toBe("");
  });

  it("негативный: staged-число частоты НЕ в элементе текущего значения", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    // Открываем stateless-меню частоты и выбираем 2 МГц без запуска.
    button(container, ".lnt-scope-rate-field .lnt-live-chip-btn").click();
    button(container, ".lnt-scope-rate-field [role='option'][data-value='2000000']").click();
    await flush();

    // Слот текущего значения остаётся применённой частотой; цель — в маркере.
    const slot = container.querySelector("[data-slot='rate']");
    expect(slot?.textContent).toBe("8 МГц");
    expect(container.querySelector<HTMLElement>('[data-live-mark="rate"]')?.textContent).toBe(
      "→ 2 МГц",
    );

    // Запуск использует staged-цель; после применения слот обновляется.
    button(container, "#lnt-scope-run").click();
    await flush();
    expect(log.starts[0]?.body).toMatchObject({ sample_rate_hz: 2_000_000 });
    emitAll("heartbeat", RUNNING);
    await flush();
    expect(slot?.textContent).toBe("2 МГц");
  });

  it("задача 15: линия триггера на экране; ИЗМЕР несёт курсоры/автосет/сброс", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    // Линия триггера — DOM-оверлей на viewport экрана, синхронна полю.
    const line = container.querySelector<HTMLElement>("[data-trigger-line]");
    expect(line).toBeInstanceOf(HTMLElement);
    expect(line?.closest(".lnt-scope-viewport")).toBeInstanceOf(HTMLElement);
    const level = container.querySelector<HTMLInputElement>("#lnt-scope-level");
    if (level === null) throw new Error("нет поля уровня");
    level.value = "1";
    level.dispatchEvent(new Event("change", { bubbles: true }));
    expect(line?.getAttribute("aria-valuenow")).toBe("1");

    // ИЗМЕР: тумблер курсоров + ридаут Δt/ΔV; кнопки действий с эхом.
    const cursors = container.querySelector('[data-local="cursors"]');
    expect(cursors?.querySelectorAll("button")).toHaveLength(2);
    expect(cursors?.querySelector(".readout-grid")).toBeInstanceOf(HTMLElement);
    const autoset = container.querySelector('[data-action="autoset"] button');
    expect(autoset?.textContent).toBe("Автосет");
    const reset = container.querySelector('[data-action="reset"] button');
    expect(reset?.textContent).toBe("Сброс");
    expect(container.querySelector('[data-echo="autoset"]')).toBeInstanceOf(HTMLElement);
    expect(container.querySelector('[data-echo="reset"]')).toBeInstanceOf(HTMLElement);
  });

  it("задача 15: 409 запуска — баннер с переходом; Run возвращается в исходное", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const { container } = mountTab(log, { state: { ...IDLE }, start409: true });
    await flush();

    button(container, "#lnt-scope-run").click();
    await flush();

    // Баннер конфликта в статус-зоне: текст зеркала + кнопка перехода.
    const banner = container.querySelector<HTMLElement>(".lnt-live-conflict");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("Запуск уже выполняется на вкладке «Спектроанализатор»");
    expect(banner?.textContent).toContain(LIVE_ALREADY_RUNNING_RU);
    // Run не залип: кнопка доступна, кластер в idle.
    const run = container.querySelector<HTMLButtonElement>("#lnt-scope-run");
    expect(run?.disabled).toBe(false);
    expect(run?.getAttribute("aria-checked")).toBe("false");
    expect(container.querySelector(".lnt-live-runctl")?.getAttribute("data-run-state")).toBe(
      "idle",
    );

    // Кнопка «Перейти и остановить»: стоп + переход на вкладку-конкурента.
    const goto = banner?.querySelector<HTMLButtonElement>(".lnt-live-conflict button");
    if (!(goto instanceof HTMLButtonElement)) throw new Error("нет кнопки перехода");
    goto.click();
    await flush();
    expect(log.stops).toBe(1);
    expect(window.location.hash).toBe("#/sa");
  });
});
