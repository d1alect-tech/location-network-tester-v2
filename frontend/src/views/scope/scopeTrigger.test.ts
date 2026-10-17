/** Todo 9 RED: триггер-панель вкладки «Осциллограф» — источник, полярность,
 * уровень с валидацией и режим auto/normal/single + rate-селектор таблицы
 * прибора. Честные метки: связь входов только DC, панель не обещает
 * AC-связь, holdoff и предтриггер. Единица — вьюха (scopeTrigger) без сети;
 * интеграция — монтированный workspace: mode/level при живом захвате шлют
 * POST /api/live/config (nonce, триггер целиком), валидный уровень на ходу,
 * невалидный — ошибка без POST и без старта; SINGLE — ровно один кадр и
 * стоп (сервер освобождает прибор, панель подтверждает остановку). */

import { afterEach, describe, expect, it, vi } from "vitest";
import { LntApiClient } from "../../api/client";
import { createLiveApi } from "../../api/client-live";
import type {
  LiveChannelSeries,
  LiveFramePayload,
  LiveStatePayload,
  LiveTrigger,
} from "../../api/types-live";
import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { buildScopeRateField } from "./scopeRateField";
import { buildScopeTriggerSection } from "./scopeTrigger";
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
  configs: Array<{ body: LiveTrigger; nonce: string | undefined }>;
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
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      log.starts.push({ body, nonce: headers["X-LNT-Mutation-Nonce"] });
      // Ответ несёт ДЕЙСТВУЮЩИЙ триггер сервиса (state_payload): зеркало старта.
      live.state = { ...RUNNING, trigger: (body.trigger as LiveTrigger | undefined) ?? TRIGGER };
      return json(live.state);
    }
    if (url.startsWith("/api/live/stop") && init?.method === "POST") {
      log.stops += 1;
      live.state = STOPPED;
      return json(live.state);
    }
    if (url.startsWith("/api/live/config") && init?.method === "POST") {
      if (live.state.state !== "running") {
        return json({ detail: "живой режим не запущен: сначала start" }, 409);
      }
      const body = JSON.parse(String(init.body)) as LiveTrigger;
      log.configs.push({ body, nonce: headers["X-LNT-Mutation-Nonce"] });
      live.state = { ...RUNNING, trigger: body };
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
  const workspace = mountScopeWorkspace(container, {
    client: new LntApiClient(fetchImpl),
    live: createLiveApi(new LntApiClient(fetchImpl)),
  });
  cleanups.push(() => workspace.dispose());
  return container;
}

function segButton(root: HTMLElement, attr: string, value: string): HTMLButtonElement {
  const button = root.querySelector(`button[${attr}="${value}"]`);
  if (!(button instanceof HTMLButtonElement)) throw new Error(`нет кнопки ${attr}=${value}`);
  return button;
}

function levelInput(root: HTMLElement): HTMLInputElement {
  const input = root.querySelector<HTMLInputElement>("#lnt-scope-level");
  if (input === null) throw new Error("нет поля #lnt-scope-level");
  return input;
}

function setLevel(root: HTMLElement, raw: string): void {
  const input = levelInput(root);
  input.value = raw;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

afterEach(() => {
  for (const cleanup of cleanups) cleanup();
  cleanups.length = 0;
  vi.unstubAllGlobals();
  FakeLiveEventSource.instances = [];
  document.body.replaceChildren();
});

describe("scopeTrigger view (Todo 9)", () => {
  it("renders honest labels: DC coupling, available modes only, instrument rate table", () => {
    const changes: LiveTrigger[] = [];
    const panel = buildScopeTriggerSection({ onTriggerChange: (trigger) => changes.push(trigger) });
    document.body.append(panel.root);

    // Панель V6 с заголовком; группа режимов доступна клавиатуре (role=group).
    expect(panel.root.querySelector(".panel-title")?.textContent).toBe("Триггер");
    expect(panel.root.querySelector('[role="group"][aria-label="Режим триггера"]')).toBeInstanceOf(
      HTMLElement,
    );

    // Источник/фронт/режим — ровно доступные значения, не больше.
    expect(segButton(panel.root, "data-trigger-source", "ch1").textContent).toBe("CH1");
    expect(segButton(panel.root, "data-trigger-source", "ch2").textContent).toBe("CH2");
    expect(segButton(panel.root, "data-trigger-slope", "rising").textContent).toBe("Подъём");
    expect(segButton(panel.root, "data-trigger-slope", "falling").textContent).toBe("Спад");
    expect(segButton(panel.root, "data-trigger-mode", "auto").textContent).toBe("Авто");
    expect(segButton(panel.root, "data-trigger-mode", "normal").textContent).toBe("Норм");
    expect(segButton(panel.root, "data-trigger-mode", "single").textContent).toBe("Одиночный");

    // Дефолт — зеркало InstrumentService: CH1, подъём, AUTO, уровень 0 В.
    expect(segButton(panel.root, "data-trigger-source", "ch1").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(segButton(panel.root, "data-trigger-slope", "rising").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(segButton(panel.root, "data-trigger-mode", "auto").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(levelInput(panel.root).value).toBe("0");
    expect(panel.getTrigger()).toEqual(DEFAULT_LIVE_START_REQUEST.trigger);

    // Уровень — число с диапазоном номинальной шкалы каналов.
    const level = levelInput(panel.root);
    expect(level.getAttribute("type")).toBe("number");
    expect(level.getAttribute("min")).toBe("-5");
    expect(level.getAttribute("max")).toBe("5");

    // Связь входов: только DC — честная метка, AC-обещания нет.
    expect(panel.root.querySelector(".lnt-scope-coupling")?.textContent).toContain("DC");

    // Честные метки: ни слова AC, holdoff или предтриггера.
    const text = panel.root.textContent ?? "";
    expect(text).not.toMatch(/\bAC\b/);
    expect(text).not.toContain("holdoff");
    expect(text).not.toContain("предтриггер");
  });

  it("rate field: чип с семью частотами прибора, слот — применённое, выбор отложен", () => {
    const field = buildScopeRateField();
    document.body.append(field.root);

    // Слот показывает применённое значение; выбор в списке — staged-цель.
    expect(field.root.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");
    expect(field.rateHz()).toBe(8_000_000);

    (field.root.querySelector(".lnt-live-chip-btn") as HTMLButtonElement).click();
    const labels = [...field.root.querySelectorAll("[role='option']")].map(
      (option) => option.querySelector(".lnt-live-opt-text")?.textContent,
    );
    expect(labels).toEqual(["100 кГц", "200 кГц", "500 кГц", "1 МГц", "2 МГц", "4 МГц", "8 МГц"]);

    (field.root.querySelector("[role='option'][data-value='500000']") as HTMLButtonElement).click();
    expect(field.rateHz()).toBe(500_000);
    // Staged ≠ текущее: слот не меняется (цель помечает стрелкой scopeStatus
    // полосы — стейджинг-реестр не часть поля).
    expect(field.root.querySelector("[data-slot='rate']")?.textContent).toBe("8 МГц");

    // Выбор применённого значения возвращает цель к базлайну (снятие стейджа —
    // маркерами ведает scopeStatus полосы, здесь — только значение поля).
    (field.root.querySelector(".lnt-live-chip-btn") as HTMLButtonElement).click();
    (
      field.root.querySelector("[role='option'][data-value='8000000']") as HTMLButtonElement
    ).click();
    expect(field.rateHz()).toBe(8_000_000);

    // selectRate — программная дорога сброса/автосета (задачи 15).
    field.selectRate(1_000_000);
    expect(field.rateHz()).toBe(1_000_000);
  });

  it("seg clicks fire onTriggerChange with the full trigger; pressed follows", () => {
    const changes: LiveTrigger[] = [];
    const panel = buildScopeTriggerSection({ onTriggerChange: (trigger) => changes.push(trigger) });
    document.body.append(panel.root);

    segButton(panel.root, "data-trigger-mode", "normal").click();
    segButton(panel.root, "data-trigger-slope", "falling").click();
    segButton(panel.root, "data-trigger-source", "ch2").click();
    expect(changes).toHaveLength(3);
    expect(changes[2]).toEqual({
      level_v: 0,
      slope: "falling",
      source: "ch2",
      mode: "normal",
      auto_timeout_s: 0.2,
    });
    expect(segButton(panel.root, "data-trigger-mode", "normal").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(segButton(panel.root, "data-trigger-mode", "auto").getAttribute("aria-pressed")).toBe(
      "false",
    );

    // Клик по уже нажатой кнопке — no-op: лишних событий нет.
    segButton(panel.root, "data-trigger-source", "ch2").click();
    expect(changes).toHaveLength(3);
  });

  it("level change fires onTriggerChange; out-of-range level — error, no callback", () => {
    const changes: LiveTrigger[] = [];
    const panel = buildScopeTriggerSection({ onTriggerChange: (trigger) => changes.push(trigger) });
    document.body.append(panel.root);

    setLevel(panel.root, "2.5");
    expect(changes).toEqual([
      { level_v: 2.5, slope: "rising", source: "ch1", mode: "auto", auto_timeout_s: 0.2 },
    ]);
    expect(panel.validationError()).toBeNull();

    // Выход за номинальную шкалу: ошибка в поле, колбэка нет.
    setLevel(panel.root, "7");
    expect(changes).toHaveLength(1);
    expect(panel.validationError()).toContain("от -5 до 5");
    const error = panel.root.querySelector("[role='alert']");
    expect(error?.textContent).toContain("от -5 до 5");
    expect(levelInput(panel.root).getAttribute("aria-invalid")).toBe("true");

    // Пустое и нечисловое — та же честная ошибка без колбэка.
    setLevel(panel.root, "");
    expect(changes).toHaveLength(1);
    expect(panel.validationError()).toContain("числом");

    // Корректное значение снимает ошибку и снова уходит колбэком.
    setLevel(panel.root, "-1.5");
    expect(changes).toHaveLength(2);
    expect(changes[1]?.level_v).toBe(-1.5);
    expect(panel.validationError()).toBeNull();
    expect(panel.root.querySelector("[role='alert']")).toBeNull();
    expect(levelInput(panel.root).getAttribute("aria-invalid")).toBe("false");
  });

  it("paintTrigger repaints controls from service truth", () => {
    const panel = buildScopeTriggerSection({ onTriggerChange: () => undefined });
    document.body.append(panel.root);

    panel.paintTrigger({
      level_v: 1.25,
      slope: "falling",
      source: "ch2",
      mode: "normal",
      auto_timeout_s: 0.2,
    });
    expect(segButton(panel.root, "data-trigger-mode", "normal").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(
      segButton(panel.root, "data-trigger-slope", "falling").getAttribute("aria-pressed"),
    ).toBe("true");
    expect(segButton(panel.root, "data-trigger-source", "ch2").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(levelInput(panel.root).value).toBe("1.25");
    expect(panel.getTrigger()).toMatchObject({ level_v: 1.25, mode: "normal" });
  });
});

describe("scope workspace wiring (Todo 9)", () => {
  it("mode change while running POSTs /api/live/config; idle — stages for next start", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();

    // Idle: конфига нет — триггер стейджится на следующий запуск.
    segButton(container, "data-trigger-mode", "normal").click();
    await flush();
    expect(log.configs).toHaveLength(0);

    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();
    expect(log.starts[0]?.body).toMatchObject({ trigger: { mode: "normal" } });
    expect(segButton(container, "data-trigger-mode", "normal").getAttribute("aria-pressed")).toBe(
      "true",
    );

    // Running: смена режима уходит конфигом целиком, с nonce.
    segButton(container, "data-trigger-mode", "single").click();
    await flush();
    expect(log.configs).toHaveLength(1);
    expect(log.configs[0]?.nonce).toBe("test-nonce");
    expect(log.configs[0]?.body).toEqual({
      level_v: 0,
      slope: "rising",
      source: "ch1",
      mode: "single",
      auto_timeout_s: 0.2,
    });
  });

  it("level change POSTs config; out-of-range level — validation error and NO POST", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();

    setLevel(container, "2.5");
    await flush();
    expect(log.configs).toHaveLength(1);
    expect(log.configs[0]?.body).toMatchObject({ level_v: 2.5, mode: "auto" });

    setLevel(container, "7");
    await flush();
    expect(log.configs).toHaveLength(1);
    const error = container.querySelector(".lnt-scope-trigger [role='alert']");
    expect(error?.textContent).toContain("от -5 до 5");
    expect(levelInput(container).getAttribute("aria-invalid")).toBe("true");
  });

  it("Run with an invalid level is rejected until the level is fixed", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();

    setLevel(container, "9");
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();
    expect(log.starts).toHaveLength(0);
    expect(container.querySelector(".lnt-scope-error-host .banner")?.textContent).toContain(
      "Уровень триггера",
    );

    setLevel(container, "0.5");
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();
    expect(log.starts).toHaveLength(1);
    expect(log.starts[0]?.body).toMatchObject({ trigger: { level_v: 0.5 } });
  });

  it("SINGLE mode: one frame, then the panel stops the instrument", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();

    segButton(container, "data-trigger-mode", "single").click();
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();
    expect(log.starts[0]?.body).toMatchObject({ trigger: { mode: "single" } });

    // Сервер отдаёт кадр на фронте (service сам освобождает прибор после него).
    FakeLiveEventSource.instances[0]?.emit("frame", frame(1));
    await flush();

    // Показан ровно один кадр; прибор остановлен ровно одним stop-ом.
    expect(container.querySelector(".lnt-scope-frame-count")?.textContent).toBe("1");
    expect(log.stops).toBe(1);
    expect(container.querySelector(".lnt-scope-state")?.getAttribute("data-live-state")).toBe(
      "stopped",
    );
    expect(container.querySelector(".lnt-scope-state")?.textContent).toContain("остановлен");
    expect((container.querySelector("#lnt-scope-run") as HTMLButtonElement).disabled).toBe(false);
    expect((container.querySelector("#lnt-scope-stop") as HTMLButtonElement).disabled).toBe(true);
  });

  it("slope and source clicks POST config with falling and ch2", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();

    segButton(container, "data-trigger-slope", "falling").click();
    await flush();
    expect(log.configs[0]?.body).toMatchObject({ slope: "falling" });

    segButton(container, "data-trigger-source", "ch2").click();
    await flush();
    expect(log.configs[1]?.body).toMatchObject({ source: "ch2", slope: "falling" });
  });

  it("remount while running paints the service trigger into the controls", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const service: LiveTrigger = {
      level_v: 1.25,
      slope: "falling",
      source: "ch2",
      mode: "normal",
      auto_timeout_s: 0.2,
    };
    const container = mountStub(log, { state: { ...RUNNING, trigger: service } });
    await flush();

    expect(segButton(container, "data-trigger-mode", "normal").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(segButton(container, "data-trigger-slope", "falling").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(segButton(container, "data-trigger-source", "ch2").getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(levelInput(container).value).toBe("1.25");
  });

  it("rate selector: staged for the next start, no config while running", async () => {
    const log: LiveLog = { starts: [], stops: 0, states: 0, configs: [] };
    const container = mountStub(log, { state: { ...IDLE } });
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();

    // На ходу частота не меняется: выбор в списке не шлёт конфиг.
    (
      container.querySelector(".lnt-scope-rate-field .lnt-live-chip-btn") as HTMLButtonElement
    ).click();
    (
      container.querySelector(
        ".lnt-scope-rate-field [role='option'][data-value='1000000']",
      ) as HTMLButtonElement
    ).click();
    await flush();
    expect(log.configs).toHaveLength(0);

    // Следующий запуск идёт выбранной частотой.
    (container.querySelector("#lnt-scope-stop") as HTMLButtonElement).click();
    await flush();
    (container.querySelector("#lnt-scope-run") as HTMLButtonElement).click();
    await flush();
    expect(log.starts).toHaveLength(2);
    expect(log.starts[0]?.body).toMatchObject({ sample_rate_hz: 8_000_000 });
    expect(log.starts[1]?.body).toMatchObject({ sample_rate_hz: 1_000_000 });
  });
});
