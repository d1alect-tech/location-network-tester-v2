/** Задача 15 RED: drag курсорных линий на uPlot-фигуре (зона-карта §8.3 —
 * слайдеры курсоров скрытый leftover, позиционирование переносится на drag
 * линий, рисует их плагин scopeCursorPaint). Hit-тест 4 линий по позициям
 * плагина (полоса 44 px, свежая геометрия на каждый pointerdown), drag
 * пишет ЖИВЫЕ слайдеры (value + input-событие — слушатели
 * scopeCursorSection живы), зажимы долей окна [0..1] и вольт ±5;
 * клавиатура: стрелки под фокусом на фигуре двигают последний потянутый
 * курсор; выключенные курсоры и отсутствие графика — drag нет; dispose
 * снимает слушатели. */

import { afterEach, describe, expect, it } from "vitest";
import { mountScopeCursorDrag } from "./scopeCursorDrag";

const BBOX = { left: 40, top: 10, width: 360, height: 240 };

/** Фальшивая геометрия: окно X 0..2 мс, домен Y ±5 В, bbox 40/10/360/240 —
 * те же пропорции, что у фальшивого uPlot в scopeCursorSection.test. */
const GEOMETRY = {
  bbox: BBOX,
  scales: { x: { min: 0, max: 0.002 } },
  valToPos: (value: number, scale: string): number => {
    if (scale === "x") return 40 + (value / 0.002) * 360;
    return 10 + 240 * (0.5 - value / 10);
  },
  posToVal: (pixel: number, scale: string): number => {
    if (scale === "x") return ((pixel - 40) / 360) * 0.002;
    return (0.5 - (pixel - 10) / 240) * 10;
  },
};

interface Sliders {
  t1: HTMLInputElement;
  t2: HTMLInputElement;
  v1: HTMLInputElement;
  v2: HTMLInputElement;
}

function makeSliders(): Sliders {
  const build = (id: string, min: number, max: number, value: string): HTMLInputElement => {
    const input = document.createElement("input");
    input.type = "range";
    input.id = id;
    input.min = String(min);
    input.max = String(max);
    input.step = "5";
    input.value = value;
    return input;
  };
  return {
    t1: build("lnt-scope-cursor-t1", 0, 1000, "250"),
    t2: build("lnt-scope-cursor-t2", 0, 1000, "750"),
    v1: build("lnt-scope-cursor-v1", -500, 500, "-100"),
    v2: build("lnt-scope-cursor-v2", -500, 500, "100"),
  };
}

function mountDrag(
  overrides: {
    geometry?: () => typeof GEOMETRY | null;
    enabled?: () => boolean;
  } = {},
) {
  const figure = document.createElement("div");
  figure.className = "lnt-scope-figure";
  const sliders = makeSliders();
  document.body.append(figure, sliders.t1, sliders.t2, sliders.v1, sliders.v2);
  const events: string[] = [];
  for (const input of [sliders.t1, sliders.t2, sliders.v1, sliders.v2]) {
    input.addEventListener("input", () => events.push(input.id));
  }
  const handle = mountScopeCursorDrag({
    figure,
    geometry: overrides.geometry ?? (() => GEOMETRY),
    sliders,
    enabled: overrides.enabled ?? (() => true),
  });
  return { figure, sliders, events, dispose: handle.dispose };
}

function pointer(target: Element, type: string, x: number, y: number): void {
  target.dispatchEvent(
    new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, buttons: 1 }),
  );
}

function key(target: Element, keyName: string): void {
  target.dispatchEvent(new KeyboardEvent("keydown", { key: keyName, bubbles: true }));
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("scopeCursorDrag: drag линий курсоров", () => {
  it("drag T1 (полоса 44 px): пишет слайдер value + input", () => {
    const { figure, sliders, events } = mountDrag();
    // T1 на x=130 (доля 0.25); захват в 21 px от линии — ещё попадание.
    pointer(figure, "pointerdown", 151, 130);
    pointer(figure, "pointermove", 200, 130);
    pointer(figure, "pointerup", 200, 130);

    // Доля (200−40)/360 → 444‰, округление к шагу слайдера 5 → 445.
    expect(sliders.t1.value).toBe("445");
    expect(events).toContain("lnt-scope-cursor-t1");
  });

  it("drag V1: вольты из позиции пишутся в слайдер с зажимом ±5 В", () => {
    const { figure, sliders, events } = mountDrag();
    // V1 на y=154 (−1 В); тяну к y=120 → ≈0,417 В → 40 (шаг 5 от сотых).
    pointer(figure, "pointerdown", 40, 154);
    pointer(figure, "pointermove", 40, 120);
    pointer(figure, "pointerup", 40, 120);
    expect(sliders.v1.value).toBe("40");
    expect(events).toContain("lnt-scope-cursor-v1");

    // Зажимы: старт на линии V2 (y=106), увод за края экрана.
    pointer(figure, "pointerdown", 40, 106);
    pointer(figure, "pointermove", 40, -100);
    expect(sliders.v2.value).toBe("500");
    pointer(figure, "pointermove", 40, 400);
    expect(sliders.v2.value).toBe("-500");
  });

  it("за пределами hit-полосы захвата нет (30 px от всех линий)", () => {
    const { figure, sliders } = mountDrag();
    pointer(figure, "pointerdown", 160, 130);
    pointer(figure, "pointermove", 250, 130);
    pointer(figure, "pointerup", 250, 130);
    expect(sliders.t1.value).toBe("250");
    expect(sliders.v1.value).toBe("-100");
    expect(sliders.v2.value).toBe("100");
  });

  it("доля окна зажимается в [0..1] при drag T-линии за края", () => {
    const { figure, sliders } = mountDrag();
    pointer(figure, "pointerdown", 130, 100);
    pointer(figure, "pointermove", -50, 100);
    expect(sliders.t1.value).toBe("0");
    pointer(figure, "pointermove", 500, 100);
    expect(sliders.t1.value).toBe("1000");
    pointer(figure, "pointercancel", 500, 100);
  });

  it("курсоры выключены (тумблер Выкл) — линии не тянутся", () => {
    const { figure, sliders } = mountDrag({ enabled: () => false });
    pointer(figure, "pointerdown", 130, 100);
    pointer(figure, "pointermove", 200, 130);
    expect(sliders.t1.value).toBe("250");
  });

  it("нет графика (кадра нет) — drag нет", () => {
    const { figure, sliders } = mountDrag({ geometry: () => null });
    pointer(figure, "pointerdown", 130, 100);
    pointer(figure, "pointermove", 200, 130);
    expect(sliders.t1.value).toBe("250");
  });

  it("клавиатура: стрелки двигают последний потянутый курсор", () => {
    const { figure, sliders } = mountDrag();
    // До первого drag стрелки молчат: выбранной линии нет.
    figure.focus();
    key(figure, "ArrowRight");
    expect(sliders.t1.value).toBe("250");

    // T1 последний: → двигает долю окна на шаг слайдера.
    pointer(figure, "pointerdown", 130, 100);
    pointer(figure, "pointermove", 200, 130);
    key(figure, "ArrowRight");
    expect(sliders.t1.value).toBe("450");
    key(figure, "ArrowLeft");
    expect(sliders.t1.value).toBe("445");

    // V1 после его drag: ↑/↓ двигают вольты.
    pointer(figure, "pointerdown", 40, 154);
    pointer(figure, "pointermove", 40, 120);
    key(figure, "ArrowUp");
    expect(sliders.v1.value).toBe("45");
    key(figure, "ArrowDown");
    expect(sliders.v1.value).toBe("40");
  });

  it("dispose: слушатели сняты — drag после dispose не пишет слайдеры", () => {
    const { figure, sliders, dispose } = mountDrag();
    dispose();
    pointer(figure, "pointerdown", 130, 100);
    pointer(figure, "pointermove", 200, 130);
    expect(sliders.t1.value).toBe("250");
  });
});
