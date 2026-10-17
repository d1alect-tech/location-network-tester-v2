/** r4-final f1 (интеграционно): drag экранной линии при running коалесцирует
 * POST /api/live/config — 20 шагов 0,01 В = один конфиг с финальным уровнем;
 * порядок ответов не гарантирован, устаревший ответ не затирает более новое
 * состояние (guard по счётчику запросов), истина остаётся за SSE-событием.
 * Полный монтаж воркспейс+полоса, как в scopeAutoset.test.ts: линия живёт
 * в полосе, POST уходит из воркспейса. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type { LiveStatePayload } from "../../api/types-live";
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

/** Ответ конфига с уровнем — для теста порядка применения ответов. */
const runningAt = (levelV: number): LiveStatePayload => ({
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: { level_v: levelV, slope: "rising", source: "ch1", mode: "auto", auto_timeout_s: 0.2 },
});

const RECT = {
  width: 400,
  height: 200,
  top: 0,
  left: 0,
  right: 400,
  bottom: 200,
  x: 0,
  y: 0,
  toJSON: () => "",
} as DOMRect;

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
  starts: number;
  stops: number;
  states: number;
  configs: Array<Record<string, unknown>>;
}

/** Конфиг-ответы можно подменить отложенными (управление порядком). */
function liveStubFetch(
  log: LiveLog,
  live: { state: LiveStatePayload },
  configResponses?: Array<Promise<LiveStatePayload>>,
): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const json = (body: unknown, status = 200): Response =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/device/state")) return json(DEVICE_READY);
    if (url.startsWith("/api/live/state")) {
      log.states += 1;
      return json(live.state);
    }
    if (url.startsWith("/api/live/start") && init?.method === "POST") {
      log.starts += 1;
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
      const response = configResponses?.[log.configs.length - 1];
      if (response !== undefined) return response.then((state) => json(state));
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
  live: { state: LiveStatePayload },
  configResponses?: Array<Promise<LiveStatePayload>>,
): HTMLElement {
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(log, live, configResponses);
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

function pointer(target: Element, type: string, x: number, y: number): void {
  target.dispatchEvent(
    new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, buttons: 1 }),
  );
}

function triggerLineOf(container: HTMLElement): HTMLElement {
  const line = container.querySelector<HTMLElement>("[data-trigger-line]");
  if (line === null) throw new Error("нет линии триггера");
  return line;
}

function levelFieldOf(container: HTMLElement): HTMLInputElement {
  const field = container.querySelector<HTMLInputElement>("#lnt-scope-level");
  if (field === null) throw new Error("нет поля уровня");
  return field;
}

function rectSpy(container: HTMLElement): void {
  const viewport = container.querySelector<HTMLElement>(".lnt-scope-viewport");
  if (viewport === null) throw new Error("нет viewport");
  vi.spyOn(viewport, "getBoundingClientRect").mockReturnValue(RECT);
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("scopeTriggerDrag: конфиг триггера при drag линии (r4-final f1)", () => {
  it("drag на 20 шагов = один POST /api/live/config с финальным уровнем", async () => {
    const log: LiveLog = { starts: 0, stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    button(container, "#lnt-scope-run").click();
    await flush();
    rectSpy(container);
    const line = triggerLineOf(container);
    const level = levelFieldOf(container);

    // 20 шагов по 2 px (0,1 В на шаг): поле живое, конфигов нет.
    pointer(line, "pointerdown", 200, 100);
    for (let i = 1; i <= 20; i += 1) pointer(line, "pointermove", 200, 100 - 2 * i);
    await flush();
    expect(level.value).toBe("2");
    expect(log.configs).toHaveLength(0);

    // Settle: финальный уровень уходит одним конфигом.
    pointer(line, "pointerup", 200, 60);
    await flush();
    expect(log.configs).toHaveLength(1);
    expect(log.configs[0]).toMatchObject({ level_v: 2, mode: "auto", slope: "rising" });
  });

  it("порядок: поздний устаревший ответ конфига не затирает новый уровень", async () => {
    const deferred: Array<(state: LiveStatePayload) => void> = [];
    const configResponses = [0, 1].map(
      () =>
        new Promise<LiveStatePayload>((resolve) => {
          deferred.push(resolve);
        }),
    );
    const log: LiveLog = { starts: 0, stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } }, configResponses);
    await flush();
    button(container, "#lnt-scope-run").click();
    await flush();
    const level = levelFieldOf(container);

    level.value = "1";
    level.dispatchEvent(new Event("change", { bubbles: true }));
    level.value = "2";
    level.dispatchEvent(new Event("change", { bubbles: true }));
    await flush();
    expect(log.configs).toHaveLength(2);

    // Новейший ответ применяется первым — панель видит уровень 2.
    deferred[1]?.(runningAt(2));
    await flush();
    expect(level.value).toBe("2");

    // Поздний ответ первого запроса устарел: уровень не откатывается к 1.
    deferred[0]?.(runningAt(1));
    await flush();
    expect(level.value).toBe("2");
  });

  it("SSE-событие состояния после settle — истина: линия на уровне сервиса", async () => {
    const log: LiveLog = { starts: 0, stops: 0, states: 0, configs: [] };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    button(container, "#lnt-scope-run").click();
    await flush();
    rectSpy(container);
    const line = triggerLineOf(container);

    pointer(line, "pointerdown", 200, 100);
    for (let i = 1; i <= 20; i += 1) pointer(line, "pointermove", 200, 100 - 2 * i);
    pointer(line, "pointerup", 200, 60);
    await flush();
    expect(log.configs).toHaveLength(1);

    // Сердцебиение подтверждает уровень — линия остаётся на 2 В (y=38).
    emitAll("heartbeat", runningAt(2));
    await flush();
    expect(line.style.transform).toBe("translateY(38px)");
  });
});
