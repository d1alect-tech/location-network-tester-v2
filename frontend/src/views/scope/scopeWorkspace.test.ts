/** Todo 7 RED: вкладка «Осциллограф» — live-контур по контрактам routes_live.py.
 * Покрывается: монтирование скелета (статус прибора, Run/Stop, показания
 * потока); sim-бейдж по mode=sim и его скрытие при mode=real; кадры и
 * heartbeat SSE обновляют показания без остановки; кнопки Run/Stop водят
 * POST /api/live/start|stop с nonce; правило остановки — авто-stop только
 * при выходе из группы маршрутов {scope, sa}, смена query того же маршрута
 * поток не трогает. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../../AppShell";
import { LntApiClient } from "../../api/client";
import { LIVE_ROUTE_GROUP, createLiveApi, rebindSharedLiveApi } from "../../api/client-live";
import type {
  LiveChannelSeries,
  LiveFramePayload,
  LiveStatePayload,
  LiveTrigger,
} from "../../api/types-live";
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
const STOPPED: LiveStatePayload = {
  state: "stopped",
  mode: "sim",
  busy_reason: null,
  trigger: TRIGGER,
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
      live.state = RUNNING;
      return json(live.state);
    }
    if (url.startsWith("/api/live/stop") && init?.method === "POST") {
      log.stops += 1;
      live.state = STOPPED;
      return json(live.state);
    }
    return json({ detail: "неизвестный маршрут" }, 404);
  }) as typeof fetch;
}

function series(points: number, amplitude: number): LiveChannelSeries {
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  for (let i = 0; i < points; i += 1) {
    time_s.push((i / points) * 0.001);
    voltage_v.push(amplitude * Math.sin((i / points) * Math.PI * 2));
  }
  return { time_s, voltage_v, point_count: points };
}

function frame(index: number): LiveFramePayload {
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
    ch1: series(8, 1),
    ch2: series(8, 0.5),
  };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

const cleanups: Array<() => void> = [];

function mountStub(log: LiveLog, live: { state: LiveStatePayload }): HTMLElement {
  // jsdom не реализует EventSource — глобал подменяется фальшивым классом.
  vi.stubGlobal("EventSource", FakeLiveEventSource);
  const container = document.createElement("div");
  document.body.append(container);
  const fetchImpl = liveStubFetch(log, live);
  cleanups.push(
    mountScopeWorkspace(container, {
      client: new LntApiClient(fetchImpl),
      live: createLiveApi(new LntApiClient(fetchImpl)),
    }),
  );
  return container;
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("scopeWorkspace skeleton (Todo 7)", () => {
  it("mounts status panel, Run/Stop controls and empty readout", async () => {
    // Given: вкладка без железа — live не запущен, режим симуляции.
    const log: LiveLog = { starts: [], stops: 0, states: 0 };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();

    // Then: скелет смонтирован, кнопки в начальном состоянии, подписка открыта.
    const root = container.querySelector(".lnt-scope-workspace");
    expect(root).toBeInstanceOf(HTMLElement);
    expect(root?.getAttribute("role")).toBe("region");
    expect(root?.getAttribute("aria-label")).toBe("Осциллограф");
    expect(container.querySelector("h2")?.textContent).toBe("Осциллограф");
    expect(container.querySelector(".lnt-scope-device")?.textContent).toContain(
      "Устройство: ready",
    );
    const run = container.querySelector("#lnt-scope-run");
    expect(run).toBeInstanceOf(HTMLButtonElement);
    expect(run?.textContent).toBe("Запустить");
    const stop = container.querySelector("#lnt-scope-stop");
    expect(stop).toBeInstanceOf(HTMLButtonElement);
    expect(stop?.textContent).toBe("Остановить");
    expect((stop as HTMLButtonElement).disabled).toBe(true);
    expect(container.querySelector(".lnt-scope-frame-count")?.textContent).toBe("—");
    expect(FakeLiveEventSource.instances).toHaveLength(1);
  });

  it("shows the «Симуляция» badge for mode=sim and hides it for mode=real", async () => {
    // Given: состояние владения сообщает sim (железа нет).
    const log: LiveLog = { starts: [], stops: 0, states: 0 };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();

    const badge = container.querySelector(".lnt-scope-sim-badge");
    expect(badge).toBeInstanceOf(HTMLElement);
    expect(badge?.textContent).toBe("Симуляция");
    expect((badge as HTMLElement).hidden).toBe(false);

    // Given: объявлен real — бейдж скрыт, режим не выводится из состояния.
    const realLog: LiveLog = { starts: [], stops: 0, states: 0 };
    const realContainer = mountStub(realLog, { state: { ...IDLE, mode: "real" } });
    await flush();
    const realBadge = realContainer.querySelector(".lnt-scope-sim-badge");
    expect(realBadge).toBeInstanceOf(HTMLElement);
    expect((realBadge as HTMLElement).hidden).toBe(true);
  });

  it("Run POSTs /api/live/start with nonce; SSE frame updates the readout", async () => {
    // Given: смонтированная вкладка и открытая подписка.
    const log: LiveLog = { starts: [], stops: 0, states: 0 };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();

    // When: оператор жмёт «Запустить».
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();

    // Then: POST с nonce и зеркалом дефолтов InstrumentService.
    expect(log.starts).toHaveLength(1);
    expect(log.starts[0]?.nonce).toBe("test-nonce");
    expect(log.starts[0]?.body).toMatchObject({
      sample_rate_hz: 8_000_000,
      ch1_range_v: 5,
      ch1_probe_multiplier: 1,
      trigger: { level_v: 0, slope: "rising", source: "ch1", mode: "auto", auto_timeout_s: 0.2 },
    });
    const stateLine = container.querySelector(".lnt-scope-state");
    expect(stateLine?.getAttribute("data-live-state")).toBe("running");
    expect(stateLine?.textContent).toContain("запущен");
    expect(container.querySelector(".lnt-scope-busy")?.textContent).toContain(
      "устройство занято вкладкой",
    );
    expect((container.querySelector("#lnt-scope-stop") as HTMLButtonElement).disabled).toBe(false);

    // When: SSE приносит кадр.
    FakeLiveEventSource.instances[0]?.emit("frame", frame(7));
    await flush();

    // Then: показания потока обновлены.
    expect(container.querySelector(".lnt-scope-frame-count")?.textContent).toBe("7");
    expect(container.querySelector(".lnt-scope-rate")?.textContent).toContain("8.0 МГц");
    expect(container.querySelector(".lnt-scope-triggered")?.textContent).toContain("фронт");
  });

  it("heartbeat state refreshes the state line and buttons without a stop", async () => {
    // Given: подписка открыта, поток ещё не запускался.
    const log: LiveLog = { starts: [], stops: 0, states: 0 };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();

    // When: heartbeat объявляет реальный режим, затем захват.
    const source = FakeLiveEventSource.instances[0];
    source?.emit("heartbeat", { ...IDLE, mode: "real" });
    await flush();
    expect(container.querySelector(".lnt-scope-state")?.getAttribute("data-live-state")).toBe(
      "idle",
    );
    expect((container.querySelector(".lnt-scope-sim-badge") as HTMLElement).hidden).toBe(true);

    source?.emit("heartbeat", RUNNING);
    await flush();
    expect(container.querySelector(".lnt-scope-state")?.getAttribute("data-live-state")).toBe(
      "running",
    );
    expect((container.querySelector("#lnt-scope-stop") as HTMLButtonElement).disabled).toBe(false);
    expect(log.stops).toBe(0);
  });

  it("Stop POSTs /api/live/stop, frees the instrument and re-enables Run", async () => {
    // Given: живой режим запущен.
    const log: LiveLog = { starts: [], stops: 0, states: 0 };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();

    // When: оператор жмёт «Остановить».
    (container.querySelector("#lnt-scope-stop") as HTMLButtonElement).click();
    await flush();

    // Then: прибор освобождён, кнопка пуска снова активна.
    expect(log.stops).toBe(1);
    expect(container.querySelector(".lnt-scope-state")?.getAttribute("data-live-state")).toBe(
      "stopped",
    );
    expect(container.querySelector(".lnt-scope-state")?.textContent).toContain("остановлен");
    expect((container.querySelector("#lnt-scope-run") as HTMLButtonElement).disabled).toBe(false);
    expect((container.querySelector("#lnt-scope-stop") as HTMLButtonElement).disabled).toBe(true);
  });

  it("unmount closes the SSE stream without stopping live", async () => {
    // Given: живой режим запущен, подписка открыта.
    const log: LiveLog = { starts: [], stops: 0, states: 0 };
    vi.stubGlobal("EventSource", FakeLiveEventSource);
    const fetchImpl = liveStubFetch(log, { state: { ...IDLE } });
    const container = document.createElement("div");
    document.body.append(container);
    const cleanup = mountScopeWorkspace(container, {
      client: new LntApiClient(fetchImpl),
      live: createLiveApi(new LntApiClient(fetchImpl)),
    });
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();

    // When: вкладку размонтируют (смена маршрута внутри группы {scope, sa}).
    cleanup();

    // Then: поток закрыт, но stop не отправлен — решение за AppShell.
    expect(FakeLiveEventSource.instances[0]?.closed).toBe(true);
    expect(log.stops).toBe(0);
  });
});

describe("live route group rule (Todo 7)", () => {
  it("LIVE_ROUTE_GROUP holds the instrument tabs scope and sa (Todo 8 follows)", () => {
    expect(LIVE_ROUTE_GROUP.has("scope")).toBe(true);
    expect(LIVE_ROUTE_GROUP.has("sa")).toBe(true);
    expect(LIVE_ROUTE_GROUP.has("catalog")).toBe(false);
  });

  it("query change inside #/scope keeps the stream; leaving the group stops once", async () => {
    // Given: AppShell на #/scope, live запущен через общий singleton-клиент.
    const log: LiveLog = { starts: [], stops: 0, states: 0 };
    rebindSharedLiveApi(new LntApiClient(liveStubFetch(log, { state: { ...IDLE } })));
    vi.stubGlobal("EventSource", FakeLiveEventSource);
    document.body.replaceChildren();
    window.history.replaceState(null, "", "/");
    window.location.hash = "#/scope";
    const container = document.createElement("div");
    container.id = "app";
    document.body.append(container);
    const shell = new AppShell(container);
    cleanups.push(() => shell.dispose());
    shell.init();
    await flush();

    const workspaceBefore = container.querySelector(".lnt-scope-workspace");
    expect(workspaceBefore).toBeInstanceOf(HTMLElement);
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();
    expect(log.starts).toHaveLength(1);

    // When: смена query того же маршрута (не выход из группы).
    window.location.hash = "#/scope?trigger=auto";
    window.dispatchEvent(new Event("hashchange"));
    await flush();

    // Then: представление не пересоздано, stop не отправлен.
    expect(container.querySelector(".lnt-scope-workspace")).toBe(workspaceBefore);
    expect(log.stops).toBe(0);

    // When: уход из группы инструментальных вкладок.
    window.location.hash = "#/catalog";
    window.dispatchEvent(new Event("hashchange"));
    await flush();

    // Then: stop ровно один, поток закрыт, вкладка размонтирована.
    expect(log.stops).toBe(1);
    expect(FakeLiveEventSource.instances[0]?.closed).toBe(true);
    expect(container.querySelector(".lnt-scope-workspace")).toBeNull();
  });
});
