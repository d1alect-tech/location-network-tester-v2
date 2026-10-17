/** Задача 15 RED: автосет — пересчёт по последнему кадру (модель
 * flat.html:2585-2597: В/дел по размаху, уровень = середина размаха с
 * зажимом ±5, частота ≈ 3 периода), эхо — список ТОЛЬКО реально изменённых
 * параметров или честное «Автонастройка: нечего менять» (guards модели
 * закрыты эхом, молчаливых no-op нет), всегда перезапуск через живые
 * кнопки кластера. Управление — только живыми слушателями DOM (клик
 * сегментов/опций, change поля уровня): Run видит новые значения. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveFramePayload, LiveStatePayload } from "../../api/types-live";
import { mountScopeStrip } from "./scopeStrip";
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

/** Кадр-синус 1250 Гц, амплитуда 1,7 В, 200 прореженных точек в окне 2 мс:
 * цель частоты = 2400·1250/3 = 1 МГц; В/дел и уровень остаются дефолтными. */
function frame(): LiveFramePayload {
  const points = 200;
  const windowS = 0.002;
  const ch1 = { time_s: [] as number[], voltage_v: [] as number[], point_count: points };
  for (let i = 0; i < points; i += 1) {
    ch1.time_s.push((i / (points - 1)) * windowS);
    ch1.voltage_v.push(1.7 * Math.sin((2 * Math.PI * 2.5 * i) / (points - 1)));
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

describe("scopeAutoset: автосет с честным эхом", () => {
  it("кадр 1250 Гц: цель частоты 1 МГц, эхо только частоты, перезапуск идёт", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    emitAll("frame", frame());
    await flush();

    button(container, '[data-action="autoset"] button').click();
    await flush();

    // Эхо называет только реально изменённое: В/дел/уровень/режим уже верны.
    expect(echoOf(container).hidden).toBe(false);
    expect(echoOf(container).textContent).toBe("Автонастройка: частота 1 МГц");
    // Всегда перезапуск: Run ушёл с пересчитанной частотой.
    expect(log.starts[0]?.body).toMatchObject({ sample_rate_hz: 1_000_000, ch1_range_v: 5 });
  });

  it("всё уже по цели — честное «нечего менять» (перезапуск всё равно идёт)", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    emitAll("frame", frame());
    await flush();
    // Цель частоты уже staged (опция 1 МГц).
    button(container, "[role='option'][data-value='1000000']").click();
    await flush();

    button(container, '[data-action="autoset"] button').click();
    await flush();

    expect(echoOf(container).textContent).toBe("Автонастройка: нечего менять");
    expect(log.starts[0]?.body).toMatchObject({ sample_rate_hz: 1_000_000 });
  });

  it("guard: кадров нет — «нечего менять», дефолты уже стоят, перезапуск есть", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();

    button(container, '[data-action="autoset"] button').click();
    await flush();

    expect(echoOf(container).textContent).toBe("Автонастройка: нечего менять");
    expect(log.starts).toHaveLength(1);
  });

  it("эхо перечисляет только реально изменённое (В/дел, уровень, фронт, частота)", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    // Уводим В/дел, уровень и фронт от вычисленных целей.
    button(container, '#lnt-scope-vdiv [data-value="1"]').click();
    const level = container.querySelector<HTMLInputElement>("#lnt-scope-level");
    if (level === null) throw new Error("нет поля уровня");
    level.value = "2.5";
    level.dispatchEvent(new Event("change", { bubbles: true }));
    button(container, '[data-trigger-slope="falling"]').click();
    emitAll("frame", frame());
    await flush();

    button(container, '[data-action="autoset"] button').click();
    await flush();

    const echo = echoOf(container).textContent ?? "";
    expect(echo).toContain("В/дел 5");
    expect(echo).toContain("уровень 0 В");
    expect(echo).toContain("фронт подъём");
    expect(echo).toContain("частота 1 МГц");
    // Применено через живые слушатели: Run видит возвращённые значения.
    expect(log.starts[0]?.body).toMatchObject({ ch1_range_v: 5 });
    const trigger = log.starts[0]?.body.trigger as Record<string, unknown> | undefined;
    expect(trigger).toMatchObject({ level_v: 0, slope: "rising" });
  });

  it("при running уровень уходит горячим конфигом, затем стоп и новый пуск", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...RUNNING } });
    await flush();
    // Кластер узнаёт running от сердцебиения своей live-подписки.
    emitAll("heartbeat", RUNNING);
    await flush();
    emitAll("frame", frame());
    await flush();

    button(container, '[data-action="autoset"] button').click();
    await flush();
    // Уровень 0 уже дефолтен: конфиг не обязателен; рестарт при running =
    // стоп → свободен → пуск (пуск подтвердится heartbeat-ом).
    emitAll("heartbeat", IDLE);
    await flush();

    expect(log.stops).toBeGreaterThanOrEqual(1);
    expect(log.starts[0]?.body).toMatchObject({ sample_rate_hz: 1_000_000 });
  });
});
