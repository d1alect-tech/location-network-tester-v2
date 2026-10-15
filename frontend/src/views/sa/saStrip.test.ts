/** Задача 16 RED: композиция SA-вкладки — полоса liveStrip поверх
 * НЕИЗМЕННОГО mountSaWorkspace (ре-парент живых узлов, слушатели живы):
 * зоны из SA-манифеста (набор ≠ scope); единый run-кластер поверх
 * #lnt-sa-run/#lnt-sa-stop (состояние из live-источника); RBW — сегменты
 * вместо select (контракт [data-sa-rbw] сохранён); span — степперы пишут
 * живые поля нативным change; staged-сценарий «изменил RBW → маркировка →
 * Run → применилось, маркировка снята»; 409 запуска — баннер с переходом
 * на вкладку-конкурента «Осциллограф»; dispose закрывает подписки. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveStatePayload } from "../../api/types-live";
import {
  LIVE_ALREADY_RUNNING_RU,
  createLiveConflictSignal,
  signalLiveConflicts,
} from "../../components/liveStrip/liveConflict";
import { mountSaStrip } from "./saStrip";
import { mountSaWorkspace } from "./saWorkspace";

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
  configs: Array<{ body: Record<string, unknown>; nonce: string | undefined }>;
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
      log.configs.push({
        body: JSON.parse(String(init.body)) as Record<string, unknown>,
        nonce: headers["X-LNT-Mutation-Nonce"],
      });
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
  // Проводка AppShell (задача 16): инструментированный live-контур — 409
  // старта уходит сигналом liveConflict, а не правкой воркспейса.
  const conflict = createLiveConflictSignal();
  const liveApi = signalLiveConflicts(createLiveApi(new LntApiClient(fetchImpl)), conflict);
  cleanups.push(
    mountSaWorkspace(container, { client: new LntApiClient(fetchImpl), live: liveApi }),
  );
  cleanups.push(mountSaStrip(container, { live: liveApi, conflictSignal: conflict }));
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

describe("saStrip: полоса поверх воркспейса (задача 16)", () => {
  it("SA-зоны рендерятся из SA-манифеста; набор ≠ scope; узлы ре-парентятся", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    const zones = [
      ...new Set(
        [...container.querySelectorAll("[data-zone]")]
          .map((n) => (n as HTMLElement).dataset.zone)
          .filter((zone): zone is string => zone !== undefined),
      ),
    ];
    expect(zones).toEqual(["span", "rbw", "run", "traces", "markers", "peaks"]);
    // Набор зон ≠ scope: scope-only зон нет, SA-only — есть.
    const scopeZones = new Set(["vert", "horiz", "trig", "measure"]);
    for (const zone of zones) expect(scopeZones.has(zone)).toBe(false);
    for (const zone of ["span", "rbw", "traces", "markers", "peaks"]) {
      expect(zones).toContain(zone);
    }

    // Линия 1: ПОЛОСА + RBW + ЗАПУСК; линия 2: ТРАССЫ + МАРКЕРЫ + ПИКИ.
    const line1 = container.querySelector('[data-band-line="1"]');
    const line2 = container.querySelector('[data-band-line="2"]');
    expect(line1?.querySelector('[data-zone="span"]')).toBeInstanceOf(HTMLElement);
    expect(line1?.querySelector('[data-zone="rbw"]')).toBeInstanceOf(HTMLElement);
    expect(line2?.querySelector('[data-zone="traces"]')).toBeInstanceOf(HTMLElement);

    // Ре-парент живых узлов: кнопки пуска в ЗАПУСК, поля полосы в ПОЛОСА,
    // RBW-сегменты в RBW, тумблеры трасс и действия — в свои зоны.
    expect(
      container.querySelector('[data-zone="run"]')?.querySelector("#lnt-sa-run"),
    ).toBeInstanceOf(HTMLButtonElement);
    const spanZone = container.querySelector('[data-zone="span"]');
    expect(spanZone?.querySelector("[data-sa-band-low]")).toBeInstanceOf(HTMLInputElement);
    expect(spanZone?.querySelector("[data-sa-band-high]")).toBeInstanceOf(HTMLInputElement);
    expect(
      container.querySelector('[data-zone="rbw"]')?.querySelector("[data-sa-rbw]"),
    ).toBeInstanceOf(HTMLElement);
    expect(
      container.querySelector('[data-zone="rbw"]')?.querySelectorAll("[data-sa-rbw] button"),
    ).toHaveLength(5);
    expect(
      container.querySelector('[data-zone="traces"]')?.querySelector(".lnt-sa-trace-toggles"),
    ).toBeInstanceOf(HTMLElement);
    expect(
      container.querySelector('[data-zone="traces"]')?.querySelector("#lnt-sa-clear"),
    ).toBeInstanceOf(HTMLButtonElement);
    expect(
      container.querySelector('[data-zone="markers"]')?.querySelector("#lnt-sa-markers-clear"),
    ).toBeInstanceOf(HTMLButtonElement);
    expect(
      container.querySelector('[data-zone="peaks"]')?.querySelector("#lnt-sa-peak-search"),
    ).toBeInstanceOf(HTMLButtonElement);

    // Воркспейс помечен режимом полосы (компактный leftover).
    expect(
      container.querySelector(".lnt-sa-workspace")?.classList.contains("lnt-sa-strip-mode"),
    ).toBe(true);

    // Подписки вкладки: воркспейс + run-кластер + saStatus.
    expect(FakeLiveEventSource.instances).toHaveLength(3);
  });

  it("единый run-кластер: running → «СТОП» в паре; dispose отписывается", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    const run = container.querySelector<HTMLButtonElement>("#lnt-sa-run");
    const stop = container.querySelector<HTMLButtonElement>("#lnt-sa-stop");
    expect(run?.textContent).toContain("ЗАПУСК");
    expect(stop?.textContent).toContain("СТОП");
    expect(run?.getAttribute("role")).toBe("switch");
    expect(stop?.getAttribute("aria-checked")).toBe("true");

    run?.click();
    await flush();
    emitAll("heartbeat", RUNNING);
    await flush();

    expect(stop?.getAttribute("aria-checked")).toBe("false");
    expect(run?.getAttribute("aria-checked")).toBe("true");
    // Полоса не владеет run-состоянием: доступность кнопок — работа воркспейса.
    expect(run?.disabled).toBe(true);
    expect(container.querySelector(".lnt-live-runctl")?.getAttribute("data-run-state")).toBe(
      "running",
    );

    for (const cleanup of cleanups) cleanup();
    cleanups.length = 0;
    expect(FakeLiveEventSource.instances.every((source) => source.closed)).toBe(true);
    emitAll("heartbeat", RUNNING);
    expect(run?.getAttribute("aria-checked")).toBe("true");
  });

  it("staged-сценарий: изменил RBW → маркировка → Run → SA-конфиг применил, снято", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    // When: оператор жмёт сегмент «100» без запуска.
    button(container, '[data-zone="rbw"] [data-value="100"]').click();
    await flush();

    // Then: маркировка staged — маркер, строка, бейдж.
    const mark = container.querySelector<HTMLElement>('[data-live-mark="rbw"]');
    expect(mark?.hidden).toBe(false);
    expect(mark?.textContent).toBe("→ 100 Гц");
    expect(container.querySelector("[data-staged-line]")?.textContent).toContain(
      "применится при следующем запуске",
    );
    const badge = container.querySelector<HTMLElement>(".lnt-live-runbadge");
    expect(badge?.hidden).toBe(false);

    // When: запуск применяет staged (Run читает селекторы воркспейса).
    button(container, "#lnt-sa-run").click();
    await flush();
    const saConfig = log.configs.at(-1)?.body as { sa?: Record<string, unknown> } | undefined;
    expect(saConfig?.sa).toMatchObject({ rbw_hz: 100 });
    emitAll("heartbeat", RUNNING);
    await flush();

    // Then: маркировка снята.
    expect(mark?.hidden).toBe(true);
    expect(badge?.hidden).toBe(true);
    expect(container.querySelector("[data-staged-line]")?.textContent).toBe("");
  });

  it("степперы полосы пишут живые поля нативным change: Run видит значения", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountTab(log, { state: { ...IDLE } });
    await flush();

    const high = container.querySelector<HTMLInputElement>("[data-sa-band-high]");
    if (high === null) throw new Error("нет поля конца полосы");
    const plus = high
      .closest(".lnt-live-stepper")
      ?.querySelector<HTMLButtonElement>('[data-step-dir="plus"]');
    if (plus === null || plus === undefined) throw new Error("нет кнопки + у конца полосы");

    // Шаг от середины диапазона: живое поле обновляется нативным change.
    high.value = "3000000";
    plus.click();
    await flush();

    expect(high.value).toBe("3001000");
    expect(log.configs.length).toBe(0);

    // Run читает селекторы воркспейса: степпер-запись уходит в SA-конфиг.
    button(container, "#lnt-sa-run").click();
    await flush();
    const saConfig = log.configs.at(-1)?.body as { sa?: Record<string, unknown> } | undefined;
    expect(saConfig?.sa).toMatchObject({ band_high_hz: 3_001_000 });

    // Зажим степпера — Найквист дефолтного старта (8 МГц / 2): за потолок
    // степпер не шагает (типинг остаётся свободным — 422 отдаёт сервер).
    high.value = "4000000";
    plus.click();
    expect(high.value).toBe("4000000");
  });

  it("409 запуска — баннер с переходом на «Осциллограф»; Run возвращается в исходное", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const { container } = mountTab(log, { state: { ...IDLE }, start409: true });
    await flush();

    button(container, "#lnt-sa-run").click();
    await flush();

    // Баннер конфликта в статус-зоне: текст зеркала + кнопка перехода.
    const banner = container.querySelector<HTMLElement>(".lnt-live-conflict");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("Запуск уже выполняется на вкладке «Осциллограф»");
    expect(banner?.textContent).toContain(LIVE_ALREADY_RUNNING_RU);
    const run = container.querySelector<HTMLButtonElement>("#lnt-sa-run");
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
    expect(window.location.hash).toBe("#/scope");
  });
});
