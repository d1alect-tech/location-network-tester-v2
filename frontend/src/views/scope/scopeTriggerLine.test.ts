/** Задача 15 RED: экранная линия триггера — DOM-оверлей поверх viewport
 * экрана осциллографа (номинальная шкала ±5 В). Drag (hit-полоса 44 px,
 * зажим ±5) пишет СУЩЕСТВУЮЩЕЕ поле #lnt-scope-level нативным change —
 * живой слушатель scopeTrigger срабатывает, дублирования POST нет; поле →
 * линия и линия → поле синхронны; клавиатура на линии: ←/→/↓/↑ ±0,1,
 * PgUp/PgDn ±1, Home/End ∓/±5; пока поле в фокусе, drag его не затирает
 * (контракт зоны); истина сервиса при running; dispose снимает всё. */

import { afterEach, describe, expect, it, vi } from "vitest";
import type { LiveStatePayload, LiveWatchHandlers } from "../../api/types-live";
import { mountScopeTriggerLine } from "./scopeTriggerLine";

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

const RUNNING: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: { level_v: 1.5, slope: "rising", source: "ch1", mode: "auto", auto_timeout_s: 0.2 },
};

const IDLE: LiveStatePayload = { state: "idle", mode: "sim", busy_reason: null, trigger: null };

function fakeLive() {
  let handlers: LiveWatchHandlers | null = null;
  let open = false;
  return {
    source: {
      watchFrames: (next: LiveWatchHandlers) => {
        handlers = next;
        open = true;
        return {
          close: () => {
            open = false;
          },
        };
      },
    },
    get open() {
      return open;
    },
    emitState(state: LiveStatePayload): void {
      handlers?.onState(state);
    },
  };
}

function mountLine() {
  const viewport = document.createElement("div");
  viewport.className = "lnt-scope-viewport";
  const field = document.createElement("input");
  field.id = "lnt-scope-level";
  field.type = "number";
  field.value = "0";
  document.body.append(field, viewport);
  vi.spyOn(viewport, "getBoundingClientRect").mockReturnValue(RECT);
  const live = fakeLive();
  const handle = mountScopeTriggerLine({ viewport, field, live: live.source });
  const line = viewport.querySelector<HTMLElement>("[data-trigger-line]");
  if (line === null) throw new Error("нет линии триггера на viewport");
  return { viewport, field, line, live, dispose: handle.dispose };
}

function pointer(target: Element, type: string, x: number, y: number): void {
  target.dispatchEvent(
    new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, buttons: 1 }),
  );
}

function key(target: Element, keyName: string): void {
  target.dispatchEvent(new KeyboardEvent("keydown", { key: keyName, bubbles: true }));
}

/** Уровень 0 В — середина экрана: полоса 44 px центрируется на y=100. */
function expectTransform(line: HTMLElement, pixels: number): void {
  expect(line.style.transform).toBe(`translateY(${pixels}px)`);
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("scopeTriggerLine: drag линии триггера", () => {
  it("монтируется на viewport с клавиатурным слайдером и серединой на 0 В", () => {
    const { line } = mountLine();
    expect(line.tabIndex).toBe(0);
    expect(line.getAttribute("role")).toBe("slider");
    expect(line.getAttribute("aria-valuemin")).toBe("-5");
    expect(line.getAttribute("aria-valuemax")).toBe("5");
    expect(line.getAttribute("aria-valuenow")).toBe("0");
    expectTransform(line, 78);
  });

  it("drag вниз на 50 px пишет поле −2,5 В нативным change; наверх — +2,5 В", () => {
    const { field, line } = mountLine();
    const changes: string[] = [];
    field.addEventListener("change", () => changes.push(field.value));
    pointer(line, "pointerdown", 200, 100);
    pointer(line, "pointermove", 200, 150);
    expect(field.value).toBe("-2.5");
    expect(changes).toEqual(["-2.5"]);
    pointer(line, "pointermove", 200, 50);
    expect(field.value).toBe("2.5");
    pointer(line, "pointerup", 200, 50);
  });

  it("drag зажимается границами ±5 В (выход за экран)", () => {
    const { field, line } = mountLine();
    pointer(line, "pointerdown", 200, 100);
    pointer(line, "pointermove", 200, 300);
    expect(field.value).toBe("-5");
    pointer(line, "pointermove", 200, -100);
    expect(field.value).toBe("5");
    pointer(line, "pointercancel", 200, 0);
  });

  it("поле → линия: change и input поля двигают линию", () => {
    const { field, line } = mountLine();
    field.value = "2";
    field.dispatchEvent(new Event("change", { bubbles: true }));
    expectTransform(line, 38);
    field.value = "-1.5";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    expectTransform(line, 108);
  });

  it("клавиатура на линии: ±0,1 / ±1 / Home/End ∓/±5", () => {
    const { field, line } = mountLine();
    line.focus();
    key(line, "ArrowDown");
    expect(field.value).toBe("-0.1");
    key(line, "ArrowRight");
    expect(field.value).toBe("0");
    key(line, "PageUp");
    expect(field.value).toBe("1");
    key(line, "PageDown");
    expect(field.value).toBe("0");
    key(line, "Home");
    expect(field.value).toBe("-5");
    key(line, "End");
    expect(field.value).toBe("5");
  });

  it("пока поле в фокусе, drag его не затирает (контракт зоны)", () => {
    const { field, line } = mountLine();
    field.focus();
    field.value = "1.2";
    pointer(line, "pointerdown", 200, 100);
    pointer(line, "pointermove", 200, 180);
    expect(field.value).toBe("1.2");
  });

  it("нечисловое поле не двигает линию", () => {
    const { field, line } = mountLine();
    field.value = "не число";
    field.dispatchEvent(new Event("change", { bubbles: true }));
    expectTransform(line, 78);
  });

  it("истина сервиса при running двигает линию; при idle линия следует полю", () => {
    const { field, live, line } = mountLine();
    live.emitState(RUNNING);
    expectTransform(line, 48);
    field.value = "0.4";
    field.dispatchEvent(new Event("change", { bubbles: true }));
    live.emitState(IDLE);
    expectTransform(line, 70);
  });

  it("dispose: линия снята, live-подписка закрыта, слушатели поля сняты", () => {
    const { field, live, line, dispose } = mountLine();
    dispose();
    expect(line.isConnected).toBe(false);
    expect(live.open).toBe(false);
    field.value = "3";
    field.dispatchEvent(new Event("change", { bubbles: true }));
    expectTransform(line, 78);
  });
});
