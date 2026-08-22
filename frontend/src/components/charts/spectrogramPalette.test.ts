/** Todo 42: палитра спектрограммы перцептивно упорядочена (строгий рост
 * относительной яркости) и различима на канве обеих тем DESIGN.md §4.1 —
 * ни одна ступень не сливается с фоном светлой/тёмной темы. */

import { describe, expect, it } from "vitest";
import { SPECTROGRAM_PALETTE, relativeLuminance } from "./spectrogramPalette";

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
