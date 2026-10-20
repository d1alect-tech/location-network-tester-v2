/** Задача 19 RED: edge-drag В/дел — drag верхней кромки «экрана» (стекло
 * осциллографа + фигура развёртки) меняет В/дел тремя детентами (5/1/0.5),
 * эхо в зоне ВЕРТ видно без клика; В/дел пишет то же поле (staged-грамматика
 * наследуется), манифест НЕ трогается (кромка — не контроль полосы).
 * АРБИТРАЖ ТРЁХ УКАЗАТЕЛЕЙ: кромка > линия триггера > курсорные линии —
 * слушатель кромки гасит событие в capture-фазе на общем предке ДО
 * листовых слушателей (существующие drag-линии не правятся, их тесты
 * зелёные без правок); вне кромок линии триггера/курсоров работают как
 * раньше. Ghost-репетиция hover — пунктир + значение, БЕЗ анимации
 * (PRM-политика: transform гасится). */

import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { el } from "../../components/primitives/dom";
import { mountScopeCursorDrag } from "./scopeCursorDrag";
import { mountScopeEdgeDrag } from "./scopeEdgeDrag";
import { VDIV_STEPS, formatVDiv } from "./scopeScale";
import { mountScopeTriggerLine } from "./scopeTriggerLine";

const VIEWPORT_RECT = {
  x: 10,
  y: 100,
  top: 100,
  right: 410,
  bottom: 400,
  left: 10,
  width: 400,
  height: 300,
  toJSON: () => ({}),
};
const FIGURE_RECT = {
  x: 10,
  y: 420,
  top: 420,
  right: 310,
  bottom: 620,
  left: 10,
  width: 300,
  height: 200,
  toJSON: () => ({}),
};

function pointer(
  target: HTMLElement,
  type: "pointerdown" | "pointermove" | "pointerup",
  x: number,
  y: number,
  buttons = 1,
): void {
  target.dispatchEvent(
    new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, cancelable: true, buttons }),
  );
}

interface Harness {
  host: HTMLElement;
  viewport: HTMLElement;
  figure: HTMLElement;
  levelField: HTMLInputElement;
  v1Slider: HTMLInputElement;
  writes: number[];
  dispose(): void;
}

/** Реальные drag-линии (триггер на стекле, курсоры на фигуре) + кромка. */
function mountHarness(vdiv = 5): Harness {
  const host = el("div", { className: "lnt-scope-workspace" });
  const viewport = el("div", { className: "lnt-scope-viewport" });
  const figure = el("div", { className: "lnt-scope-figure" });
  host.append(viewport, figure);
  document.body.append(host);
  vi.spyOn(viewport, "getBoundingClientRect").mockReturnValue(VIEWPORT_RECT);
  vi.spyOn(figure, "getBoundingClientRect").mockReturnValue(FIGURE_RECT);

  const levelField = el("input", { attrs: { type: "number" } }) as HTMLInputElement;
  document.body.append(levelField);
  const triggerLine = mountScopeTriggerLine({ viewport, field: levelField });

  const v1Slider = el("input", {
    attrs: { type: "range", min: "-500", max: "500", step: "1" },
  }) as HTMLInputElement;
  v1Slider.value = "0";
  const v2Slider = el("input", {
    attrs: { type: "range", min: "-500", max: "500", step: "1" },
  }) as HTMLInputElement;
  v2Slider.value = "0";
  const t1Slider = el("input", {
    attrs: { type: "range", min: "0", max: "1000", step: "1" },
  }) as HTMLInputElement;
  t1Slider.value = "250";
  const t2Slider = el("input", {
    attrs: { type: "range", min: "0", max: "1000", step: "1" },
  }) as HTMLInputElement;
  t2Slider.value = "750";
  // V-курсор: вольты ±5 сверху вниз, V1 = 4.9 — у верхней кромки фигуры.
  v1Slider.value = "490";
  const chart = {
    over: figure,
    bbox: {
      left: FIGURE_RECT.left,
      top: FIGURE_RECT.top,
      width: FIGURE_RECT.width,
      height: FIGURE_RECT.height,
    },
    valToPos: (value: number, scale: string) =>
      scale === "y" ? (FIGURE_RECT.height * (5 - value)) / 10 : FIGURE_RECT.width * value,
    posToVal: (pixel: number, scale: string) =>
      scale === "y" ? 5 - (pixel / FIGURE_RECT.height) * 10 : pixel / FIGURE_RECT.width,
    scales: { x: { min: 0, max: 1 } },
  };
  const cursorDrag = mountScopeCursorDrag({
    figure,
    geometry: () => chart,
    sliders: { t1: t1Slider, t2: t2Slider, v1: v1Slider, v2: v2Slider },
    enabled: () => true,
  });

  const writes: number[] = [];
  let current = vdiv;
  const edgeDrag = mountScopeEdgeDrag({
    host,
    surfaces: [viewport, figure],
    readVDiv: () => current,
    writeVDiv: (value) => {
      current = value;
      writes.push(value);
    },
  });

  return {
    host,
    viewport,
    figure,
    levelField,
    v1Slider,
    writes,
    dispose() {
      edgeDrag.dispose();
      cursorDrag.dispose();
      triggerLine.dispose();
      host.remove();
    },
  };
}

/** Позиция линии триггера (px) для уровня: (0.5 − level/10)·высота. */
function triggerLineY(level: number): number {
  return VIEWPORT_RECT.top + (0.5 - level / 10) * VIEWPORT_RECT.height;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("scopeEdgeDrag: детенты В/дел", () => {
  it("кромка стекла: тянуть вниз = мельче, зажим на 10 мВ/дел", () => {
    const h = mountHarness(5);
    pointer(h.viewport, "pointerdown", 200, VIEWPORT_RECT.top + 5);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5 + 40);
    expect(h.writes).toEqual([2]);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5 + 72);
    expect(h.writes).toEqual([2, 1]);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5 + 200);
    expect(h.writes).toEqual([2, 1, 0.05]);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5 + 300);
    expect(h.writes).toEqual([2, 1, 0.05, 0.01]);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5 + 400);
    expect(h.writes).toEqual([2, 1, 0.05, 0.01]);
    pointer(h.viewport, "pointerup", 200, VIEWPORT_RECT.top + 5 + 400);
    h.dispose();
  });

  it("тянуть вверх = крупнее; slop 4 px — клика без движения не пишет", () => {
    const h = mountHarness(0.5);
    pointer(h.viewport, "pointerdown", 200, VIEWPORT_RECT.top + 6);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 6 - 40);
    expect(h.writes).toEqual([1]);
    pointer(h.viewport, "pointerup", 200, VIEWPORT_RECT.top + 6 - 40);

    const g = mountHarness(5);
    pointer(g.viewport, "pointerdown", 200, VIEWPORT_RECT.top + 6);
    pointer(g.viewport, "pointermove", 200, VIEWPORT_RECT.top + 6 - 3);
    pointer(g.viewport, "pointerup", 200, VIEWPORT_RECT.top + 6 - 3);
    expect(g.writes).toEqual([]);
    g.dispose();
    h.dispose();
  });

  it("кромка фигуры развёртки — тот же контракт детентов", () => {
    const h = mountHarness(5);
    pointer(h.figure, "pointerdown", 100, FIGURE_RECT.top + 4);
    pointer(h.figure, "pointermove", 100, FIGURE_RECT.top + 4 + 40);
    expect(h.writes).toEqual([2]);
    pointer(h.figure, "pointerup", 100, FIGURE_RECT.top + 4 + 40);
    h.dispose();
  });
});

describe("scopeEdgeDrag: арбитраж трёх указателей", () => {
  it("кромка > линия триггера: у верхней кромки стекла линия не тянута", () => {
    const h = mountHarness(5);
    // Линия триггера на уровне 5 — у верхней кромки; pointerdown в её полосе.
    h.levelField.value = "5";
    h.levelField.dispatchEvent(new Event("input", { bubbles: true }));
    const lineY = triggerLineY(5);
    pointer(
      h.viewport.querySelector(".lnt-scope-trig-line") as HTMLElement,
      "pointerdown",
      200,
      lineY,
    );
    pointer(h.viewport, "pointermove", 200, lineY + 60);
    // Кромка забрала жест: линия не тянута, В/дел ушёл детентом вниз.
    expect(h.writes).toEqual([2]);
    h.dispose();

    // Тот же жест без кромки (уровень 0, линия в середине): линия тянута.
    const g = mountHarness(5);
    const field = g.levelField;
    field.value = "0";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    const line = g.viewport.querySelector<HTMLElement>(".lnt-scope-trig-line");
    if (line === null) throw new Error("нет линии триггера");
    pointer(line, "pointerdown", 200, triggerLineY(0));
    pointer(line, "pointermove", 200, triggerLineY(0) + 60);
    expect(field.value).not.toBe("0");
    expect(g.writes).toEqual([]);
    g.dispose();
  });

  it("кромка > курсорные линии: V1 у верхней кромки фигуры не тянут, ниже — тянут", () => {
    const h = mountHarness(5);
    // V1 = 4.9 В → у кромки: кромка выигрывает, слайдер не пишется.
    const v1Top = FIGURE_RECT.top + 2;
    pointer(h.figure, "pointerdown", 100, v1Top);
    pointer(h.figure, "pointermove", 100, v1Top + 60);
    expect(h.v1Slider.value).toBe("490");
    expect(h.writes).toEqual([2]);
    pointer(h.figure, "pointerup", 100, v1Top + 60);
    h.dispose();

    // Ниже кромки курсорные линии работают как раньше (без правок их кода).
    const g = mountHarness(5);
    const v1Slider = g.v1Slider;
    v1Slider.value = "0";
    const yMid = FIGURE_RECT.top + 100; // V1 = 0 В — середина фигуры
    pointer(g.figure, "pointerdown", 100, yMid);
    pointer(g.figure, "pointermove", 100, yMid + 40);
    expect(v1Slider.value).not.toBe("0");
    expect(g.writes).toEqual([]);
    g.dispose();
  });

  it("существующие слушатели строк НЕ редактированы: их же тесты зелёные", () => {
    // Контракт-пин: арбитраж реализован capture-слушателем на предке,
    // узлы/слушатели scopeCursorDrag и scopeTriggerLine не правятся.
    const source = readFileSync("src/views/scope/scopeCursorDrag.ts", "utf8");
    expect(source).not.toContain("scopeEdgeDrag");
    const trigSource = readFileSync("src/views/scope/scopeTriggerLine.ts", "utf8");
    expect(trigSource).not.toContain("scopeEdgeDrag");
  });
});

describe("scopeEdgeDrag: ghost-репетиция (PRM)", () => {
  it("hover в полосе кромки: пунктир + значение; уход — скрыт", () => {
    const h = mountHarness(5);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5, 0);
    const ghost = h.viewport.querySelector<HTMLElement>(".lnt-scope-edge-ghost");
    expect(ghost).toBeInstanceOf(HTMLElement);
    expect(ghost?.hidden).toBe(false);
    expect(ghost?.textContent).toContain(formatVDiv(VDIV_STEPS[0] ?? 5));
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 60, 0);
    expect(h.viewport.querySelector<HTMLElement>(".lnt-scope-edge-ghost")?.hidden).toBe(true);
    h.dispose();
  });

  it("ghost: один на обе поверхности, во время drag показывает детент", () => {
    const h = mountHarness(5);
    pointer(h.figure, "pointermove", 100, FIGURE_RECT.top + 5, 0);
    expect(h.figure.querySelector(".lnt-scope-edge-ghost")).toBeInstanceOf(HTMLElement);
    pointer(h.figure, "pointerdown", 100, FIGURE_RECT.top + 5);
    pointer(h.figure, "pointermove", 100, FIGURE_RECT.top + 5 + 40);
    const ghost = h.figure.querySelector<HTMLElement>(".lnt-scope-edge-ghost");
    expect(ghost?.hidden).toBe(false);
    expect(ghost?.textContent).toContain("2 В/дел");
    pointer(h.figure, "pointerup", 100, FIGURE_RECT.top + 5 + 40);
    h.dispose();
  });

  it("PRM: нет анимации — ни transition, ни animation, ни transform-полёта", () => {
    const h = mountHarness(5);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5, 0);
    const ghost = h.viewport.querySelector<HTMLElement>(".lnt-scope-edge-ghost");
    expect(ghost?.style.transition).toBe("");
    expect(ghost?.style.animation).toBe("");
    const css = readFileSync("src/views/scope/scope.css", "utf8");
    const rule = css.slice(
      css.indexOf(".lnt-scope-edge-ghost"),
      css.indexOf("}", css.indexOf(".lnt-scope-edge-ghost")),
    );
    expect(rule).not.toMatch(/transition|animation|transform/);
    h.dispose();
  });
});

describe("scopeEdgeDrag: dispose", () => {
  it("после dispose кромка не пишет", () => {
    const h = mountHarness(5);
    h.dispose();
    pointer(h.viewport, "pointerdown", 200, VIEWPORT_RECT.top + 5);
    pointer(h.viewport, "pointermove", 200, VIEWPORT_RECT.top + 5 + 40);
    expect(h.writes).toEqual([]);
  });
});
