/** Задача 16 RED: математ-трасса CH1−CH2 — поэлементная разность каналов
 * payload-кадра (В) как ТРЕТЬЯ серия существующего uPlot-стека (второй
 * стек не заводится); бюджет разности O(n) < 1 мс @1024; тумблер
 * local-семейства зоны ИЗМЕР; подпись честности — 8 бит, трасса просмотра,
 * без калибровочных заявлений. Измерения CH1 не меняются. */

import { describe, expect, it } from "vitest";
import type { ChartTheme } from "../../components/charts/theme";
import {
  MATH_TRACE_HINT,
  MATH_TRACE_LABEL,
  buildMathTraceToggle,
  mathDiffVolts,
  mathTagText,
  mathTraceSeries,
  mathVppV,
} from "./scopeMathTrace";
import { formatVoltsValue } from "./scopeMeasurements";

const THEME: ChartTheme = {
  accentA: "#5681ff",
  accentB: "#e68619",
  delta: "#b7a6ff",
  ok: "#3dbd8a",
  panel: "#323232",
  canvasBg: "#1d1d1d",
  fgSecondary: "#d1d1d1",
  borderSubtle: "#3f3f3f",
  fontMono: "monospace",
  fontSans: "sans-serif",
  lineWidth: 1,
};

describe("scopeMathTrace: разность каналов", () => {
  it("поэлементная разность; разная длина — по короткому ряду", () => {
    expect(mathDiffVolts([1, 2, 3], [0.5, 1])).toEqual([0.5, 1]);
    expect(mathDiffVolts([2], [5])).toEqual([-3]);
    expect(mathDiffVolts([], [])).toEqual([]);
  });

  it("размах ряда разности: max − min; без конечных отсчётов — null", () => {
    expect(mathVppV([-1, 2, 0.5])).toBe(3);
    expect(mathVppV([Number.NaN, 1])).toBe(0);
    expect(mathVppV([Number.NaN])).toBeNull();
    expect(mathVppV([])).toBeNull();
  });

  it("подпись ярлыка: размах + честность 8 бит, без калибровочных заявлений", () => {
    expect(mathTagText(1.6)).toContain(`размах ${formatVoltsValue(1.6)}`);
    expect(mathTagText(1.6)).toContain(MATH_TRACE_LABEL);
    expect(mathTagText(1.6)).toContain(MATH_TRACE_HINT);
    expect(mathTagText(null)).toContain(MATH_TRACE_LABEL);
    expect(mathTagText(null)).not.toContain("размах");
    expect(mathTagText(1.6)).not.toContain("калибров");
  });

  it("серия общего стека: токен delta, пунктир и маркер — отличие не только цветом", () => {
    const series = mathTraceSeries([1, 0, -1], THEME);
    expect(series.label).toBe(MATH_TRACE_LABEL);
    expect(series.values).toEqual([1, 0, -1]);
    expect(series.color).toBe(THEME.delta);
    expect(series.dash).toEqual([2, 3]);
    expect(series.marker).toBe("▲");
  });
});

describe("scopeMathTrace: тумблер зоны ИЗМЕР", () => {
  it("local-семейство: data-local=math, #lnt-scope-math, Вкл/Выкл", () => {
    const picks: boolean[] = [];
    const seg = buildMathTraceToggle((on) => picks.push(on));
    expect(seg.root.getAttribute("data-local")).toBe("math");
    expect(seg.root.id).toBe("lnt-scope-math");
    const buttons = [...seg.root.querySelectorAll("button")];
    expect(buttons).toHaveLength(2);
    // Семантика тумблера: клик по нажатому — no-op (живой слушатель один).
    seg.root.querySelector<HTMLButtonElement>('[data-value="on"]')?.click();
    seg.root.querySelector<HTMLButtonElement>('[data-value="on"]')?.click();
    seg.root.querySelector<HTMLButtonElement>('[data-value="off"]')?.click();
    expect(picks).toEqual([true, false]);
  });
});

describe("scopeMathTrace: бюджет кадра", () => {
  it("разность + размах 1024 сэмплов быстрее 1 мс", () => {
    const ch1 = Array.from({ length: 1024 }, (_, i) => Math.sin(i / 8));
    const ch2 = Array.from({ length: 1024 }, (_, i) => Math.cos(i / 6) * 0.5);
    const started = performance.now();
    const diff = mathDiffVolts(ch1, ch2);
    mathVppV(diff);
    const elapsedMs = performance.now() - started;
    // Пин горячего пути: O(n) разность; запас > 10×.
    expect(elapsedMs).toBeLessThan(1);
  });
});
