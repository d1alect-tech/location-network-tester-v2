/** Задача 15 RED: «Сброс» — манифест-контролы возвращаются к дефолтам
 * DEFAULT_LIVE_START_REQUEST (В/дел 5, пробник ×1, частота 8 МГц, триггер
 * 0 В / авто / CH1 / подъём) ТОЛЬКО через живые слушатели DOM (клик
 * сегментов и опции частоты, change поля уровня); staged-реестр полосы
 * очищается той же дорожкой (клик дефолта = отклонение от baseline
 * гаснет); эхо «манифест → дефолт»; перезапуска нет — только значения.
 * Сброс живёт на вкладке «Осциллограф» (зона ИЗМЕР). */

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

class FakeLiveEventSource {
  static instances: FakeLiveEventSource[] = [];
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
  starts: Array<{ body: Record<string, unknown> }>;
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
    if (url.startsWith("/api/config")) return json(CONFIG);
    if (url.startsWith("/api/device/state")) return json(DEVICE_READY);
    if (url.startsWith("/api/live/state")) {
      log.states += 1;
      return json(live.state);
    }
    if (url.startsWith("/api/live/start") && init?.method === "POST") {
      log.starts.push({ body: JSON.parse(String(init.body)) as Record<string, unknown> });
      return json(live.state);
    }
    if (url.startsWith("/api/live/stop") && init?.method === "POST") {
      log.stops += 1;
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

function pressedValue(root: ParentNode, selector: string): string | null {
  return (
    root.querySelector(`${selector} [aria-pressed="true"]`)?.getAttribute("data-value") ?? null
  );
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("scopeReset: манифест → дефолт", () => {
  it("сброс возвращает дефолты манифеста через живые слушатели", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    // Уводим всё от дефолтов.
    button(container, '#lnt-scope-vdiv [data-value="1"]').click();
    button(container, '#lnt-scope-probe [data-value="10"]').click();
    button(container, "[role='option'][data-value='2000000']").click();
    button(container, '[data-trigger-mode="single"]').click();
    button(container, '[data-trigger-source="ch2"]').click();
    button(container, '[data-trigger-slope="falling"]').click();
    const level = container.querySelector<HTMLInputElement>("#lnt-scope-level");
    if (level === null) throw new Error("нет поля уровня");
    level.value = "2.5";
    level.dispatchEvent(new Event("change", { bubbles: true }));
    await flush();

    button(container, '[data-action="reset"] button').click();
    await flush();

    // Значения == дефолтам манифеста (нажатые сегменты, поле уровня).
    expect(pressedValue(container, "#lnt-scope-vdiv")).toBe("5");
    expect(pressedValue(container, "#lnt-scope-probe")).toBe("1");
    expect(
      container.querySelector('[data-trigger-mode="auto"]')?.getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      container.querySelector('[data-trigger-source="ch1"]')?.getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      container.querySelector('[data-trigger-slope="rising"]')?.getAttribute("aria-pressed"),
    ).toBe("true");
    expect(level.value).toBe("0");
    // Staged-реестр пуст: маркер частоты погашен, строка пуста, бейдж скрыт.
    expect(container.querySelector<HTMLElement>('[data-live-mark="rate"]')?.hidden).toBe(true);
    expect(container.querySelector("[data-staged-line]")?.textContent).toBe("");
    expect(container.querySelector<HTMLElement>(".lnt-live-runbadge")?.hidden).toBe(true);
    // Эхо — «манифест → дефолт»; перезапуска сброс НЕ делает.
    const echo = container.querySelector<HTMLElement>('[data-echo="reset"]');
    expect(echo?.hidden).toBe(false);
    expect(echo?.textContent).toBe("Сброс: манифест → дефолт");
    expect(log.starts).toHaveLength(0);
  });

  it("слот частоты печатает применённый дефолт 8 МГц после сброса", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: 0 };
    const container = mountTab(log, { state: { ...IDLE } });
    await flush();
    button(container, "[role='option'][data-value='100000']").click();
    await flush();
    expect(container.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");

    button(container, '[data-action="reset"] button').click();
    await flush();
    // Слот применённого значения остаётся дефолтом; staged-цель снята.
    expect(container.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");
    expect(container.querySelector<HTMLElement>('[data-live-mark="rate"]')?.hidden).toBe(true);
  });
});
