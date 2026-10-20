import { afterEach, describe, expect, it, vi } from "vitest";
import { mountSaMarkerDrag } from "./saMarkerDrag";

afterEach(() => document.body.replaceChildren());

describe("перемещение спектрального маркера", () => {
  it("фигура — фокусируемый виджет с ролью application и подписью", () => {
    const figure = document.createElement("div");
    document.body.append(figure);
    const drag = mountSaMarkerDrag({
      figure,
      geometry: () => null,
      markers: () => [],
      select: vi.fn(),
      move: vi.fn(),
      remove: vi.fn(),
    });
    expect(figure.tabIndex).toBe(0);
    expect(figure.getAttribute("role")).toBe("application");
    expect(figure.getAttribute("aria-label")).toContain("Спектр");
    drag.dispose();
  });

  it("попадает в линию по координатам поля, выбирает и двигает без нового маркера", () => {
    const figure = document.createElement("div");
    const over = document.createElement("div");
    figure.append(over);
    document.body.append(figure);
    vi.spyOn(over, "getBoundingClientRect").mockReturnValue(new DOMRect(200, 150, 400, 200));
    const select = vi.fn();
    const move = vi.fn();
    const place = vi.fn();
    figure.addEventListener("click", place);
    const drag = mountSaMarkerDrag({
      figure,
      geometry: () => ({ over, valToPos: (v: number) => v / 10, posToVal: (v: number) => v * 10 }),
      markers: () => [{ id: 1, label: "M1", frequencyHz: 1000 }],
      select,
      move,
      remove: vi.fn(),
    });
    over.dispatchEvent(
      new MouseEvent("pointerdown", { bubbles: true, buttons: 1, clientX: 300, clientY: 200 }),
    );
    figure.dispatchEvent(
      new MouseEvent("pointermove", { bubbles: true, buttons: 1, clientX: 400, clientY: 200 }),
    );
    figure.dispatchEvent(
      new MouseEvent("pointerup", { bubbles: true, clientX: 400, clientY: 200 }),
    );
    over.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 400, clientY: 200 }));
    expect(select).toHaveBeenCalledWith(1);
    expect(move).toHaveBeenLastCalledWith(1, 2000);
    expect(place).not.toHaveBeenCalled();
    drag.dispose();
  });
});
