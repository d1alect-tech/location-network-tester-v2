import { afterEach, describe, expect, it, vi } from "vitest";
import { mountScopeGroundLine } from "./scopeGroundLine";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("независимые нулевые линии", () => {
  function setup(half = 4) {
    const figure = document.createElement("div");
    document.body.append(figure);
    vi.spyOn(figure, "getBoundingClientRect").mockReturnValue(new DOMRect(100, 200, 400, 320));
    const ground = { ch1V: 0, ch2V: 0 };
    const view = mountScopeGroundLine({
      figure,
      read: () => ground,
      write: (channel, volts) => {
        ground[channel === "ch1" ? "ch1V" : "ch2V"] = volts;
      },
      windowHalf: () => half,
    });
    return { figure, ground, view };
  }

  it("перемещает только выбранный канал с учётом положения поверхности", () => {
    const { figure, ground, view } = setup();
    const ch1 = figure.querySelector('[data-ground="ch1"]');
    ch1?.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, buttons: 1, clientY: 360 }));
    figure.dispatchEvent(
      new MouseEvent("pointermove", { bubbles: true, buttons: 1, clientY: 280 }),
    );
    figure.dispatchEvent(new MouseEvent("pointerup", { bubbles: true, clientY: 280 }));
    expect(ground).toEqual({ ch1V: 2, ch2V: 0 });
    expect(ch1?.getAttribute("aria-valuenow")).toBe("2");
    view.dispose();
  });

  it("сбрасывает CH2 отдельно и не отдаёт клавиши курсорам", () => {
    const { figure, ground, view } = setup();
    const bubbled = vi.fn();
    figure.addEventListener("keydown", bubbled);
    const ch2 = figure.querySelector('[data-ground="ch2"]');
    ch2?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }));
    expect(ground.ch2V).toBeCloseTo(0.05);
    expect(ground.ch1V).toBe(0);
    expect(bubbled).not.toHaveBeenCalled();
    ch2?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    expect(ground.ch2V).toBe(0);
    view.dispose();
  });

  it("двойной нажим сбрасывает канал до сброса совместимых mouse-событий", () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(1000);
    const { figure, ground, view } = setup();
    ground.ch1V = 1;
    const ch1 = figure.querySelector('[data-ground="ch1"]');
    ch1?.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, buttons: 1 }));
    expect(ground.ch1V).toBe(1);
    now.mockReturnValue(1200);
    ch1?.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, buttons: 1 }));
    expect(ground).toEqual({ ch1V: 0, ch2V: 0 });
    expect(ch1?.getAttribute("aria-valuenow")).toBe("0");
    view.dispose();
  });

  it("быстрый переход с CH1 на CH2 не сбрасывает нуль другого канала", () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(1000);
    const { figure, ground, view } = setup();
    ground.ch1V = 1;
    ground.ch2V = -1;
    figure
      .querySelector('[data-ground="ch1"]')
      ?.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, buttons: 1, clientY: 360 }));
    figure.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
    now.mockReturnValue(1200);
    figure
      .querySelector('[data-ground="ch2"]')
      ?.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, buttons: 1, clientY: 360 }));
    expect(ground).toEqual({ ch1V: 1, ch2V: -1 });
    view.dispose();
  });

  it("стрелка вниз двигает линию и на мелком окне 10 мВ/дел", () => {
    const { figure, ground, view } = setup(0.04);
    const ch1 = figure.querySelector('[data-ground="ch1"]');
    ch1?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    expect(ground.ch1V).toBeCloseTo(-0.0005);
    expect(ch1?.getAttribute("aria-valuenow")).toBe("-0.0005");
    view.dispose();
  });
});
