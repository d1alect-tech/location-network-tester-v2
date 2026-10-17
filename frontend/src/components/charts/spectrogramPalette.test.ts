/** Todo 42: палитра спектрограммы перцептивно упорядочена (строгий рост
 * относительной яркости) и различима на канве обеих тем DESIGN.md §4.1 —
 * ни одна ступень не сливается с фоном светлой/тёмной темы.
 *
 * Todo 5 (ui-refactor-2): live-палитра грама — копия значений замороженного
 * showcase-round2/spectrogramPalette.ts (байт-в-байт, сверка palettediff.cjs);
 * второй describe пинит равенство копий по поведению. */

import { describe, expect, it } from "vitest";
import {
  DELTA_SPAN_DB as SHOWCASE_SPAN,
  clamp01 as showcaseClamp,
  deltaColor as showcaseDelta,
  heatColor as showcaseHeat,
} from "../../showcase-round2/spectrogramPalette";
import {
  DELTA_SPAN_DB,
  SPECTROGRAM_PALETTE,
  clamp01,
  deltaColor,
  heatColor,
  relativeLuminance,
} from "./spectrogramPalette";

const LIGHT_CANVAS = 0.9; // #f4f4f4 ≈ 0.906
const DARK_CANVAS = 0.006; // #12161a ≈ 0.0065

describe("палитра матрицы спектрограммы", () => {
  it("яркость строго возрастает по ступеням (перцептивный порядок)", () => {
    const luminances = SPECTROGRAM_PALETTE.map(relativeLuminance);
    expect(luminances.every((value) => Number.isFinite(value))).toBe(true);
    for (let index = 1; index < luminances.length; index += 1) {
      const previous = luminances[index - 1];
      const current = luminances[index];
      expect(previous).toBeDefined();
      expect(current).toBeDefined();
      if (previous !== undefined && current !== undefined) {
        expect(current).toBeGreaterThan(previous);
      }
    }
  });

  it("каждая ступень отличима от канвы обеих тем (не сливается с фоном)", () => {
    for (const stop of SPECTROGRAM_PALETTE) {
      const luminance = relativeLuminance(stop);
      expect(Math.abs(luminance - LIGHT_CANVAS)).toBeGreaterThan(0.08);
      expect(Math.abs(luminance - DARK_CANVAS)).toBeGreaterThan(0.02);
    }
  });

  it("фиксированная длина шкалы для visualMap и легенды", () => {
    expect(SPECTROGRAM_PALETTE).toHaveLength(9);
  });
});

const TS = [0, 0.1, 0.25, 0.35, 0.5, 0.7, 0.85, 1, -0.2, 1.7];
const DBS = [0, 1, -1, 6, -6, 12, -12, 24, -24, 48];

describe("spectrogramPalette: копия значений равна замороженному источнику", () => {
  it("DELTA_SPAN_DB совпадает", () => {
    expect(DELTA_SPAN_DB).toBe(SHOWCASE_SPAN);
  });

  it("clamp01 совпадает на выборке", () => {
    for (const t of TS) expect(clamp01(t)).toBe(showcaseClamp(t));
  });

  it("heatColor совпадает на выборке t", () => {
    for (const t of TS) expect(heatColor(t)).toStrictEqual(showcaseHeat(t));
  });

  it("deltaColor совпадает на выборке dB", () => {
    for (const d of DBS) expect(deltaColor(d)).toStrictEqual(showcaseDelta(d));
  });
});
