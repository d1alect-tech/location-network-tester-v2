/** Todo 8 RED: масштаб живой развёртки — зеркало RANGE_CODES
 * (acquire_validation.py:18) и закон raw→V = 5.12·probe/(code<<7)
 * (adc_calibration.py:94) ровно на трёх LNT-верифицированных кодах
 * {5.0, 1.0, 0.5} В/дел; остальные 6 шагов OpenHantek вне MVP. */

import { describe, expect, it } from "vitest";
import {
  ADC_CENTER,
  DEFAULT_SCOPE_SETTINGS,
  PROBE_STEPS,
  VDIV_STEPS,
  effectiveVDiv,
  formatVDiv,
  halfSpanVolts,
  rangeCodeOf,
  rawToVolts,
  voltsPerLsb,
  yAxisRange,
} from "./scopeScale";

describe("scale law of the live sweep (Todo 8)", () => {
  it("V/div steps are exactly the three LNT-verified range codes", () => {
    expect(VDIV_STEPS).toEqual([5, 1, 0.5]);
    expect(rangeCodeOf(5)).toBe(1);
    expect(rangeCodeOf(1)).toBe(5);
    expect(rangeCodeOf(0.5)).toBe(10);
    // Шаги OpenHantek вне тройки (2, 0.2, …) — не MVP, вход отвергается.
    expect(() => rangeCodeOf(2)).toThrow();
    expect(DEFAULT_SCOPE_SETTINGS.vDiv).toBe(5);
    expect(DEFAULT_SCOPE_SETTINGS.probe).toBe(1);
  });

  it("raw→V follows 5.12·probe/(code<<7) on each verified code", () => {
    // Аналитика, не движок: полная шкала ±5.12/код В на каждом коде.
    const analytic: ReadonlyArray<readonly [number, number, number]> = [
      [5, 1, 5.12],
      [1, 5, 1.024],
      [0.5, 10, 0.512],
    ];
    for (const [vDiv, code, half] of analytic) {
      expect(voltsPerLsb(code, 1)).toBeCloseTo(5.12 / (code << 7), 12);
      expect(halfSpanVolts(vDiv, 1)).toBeCloseTo(half, 9);
      expect(rawToVolts(ADC_CENTER, vDiv, 1)).toBe(0);
      expect(rawToVolts(ADC_CENTER + 128, vDiv, 1)).toBeCloseTo(half, 6);
      expect(rawToVolts(ADC_CENTER - 128, vDiv, 1)).toBeCloseTo(-half, 6);
    }
  });

  it("probe ×10 scales volts and the label, keeping the code", () => {
    expect(PROBE_STEPS).toEqual([1, 10]);
    for (const probe of PROBE_STEPS) {
      expect(voltsPerLsb(10, probe)).toBeCloseTo((5.12 * probe) / (10 << 7), 12);
    }
    expect(halfSpanVolts(5, 10)).toBeCloseTo(51.2, 9);
    expect(effectiveVDiv(5, 10)).toBe(50);
    expect(effectiveVDiv(5, 1)).toBe(5);
  });

  it("y-axis window is symmetric around zero — stable grid", () => {
    const [min, max] = yAxisRange(1, 1);
    expect(min).toBeCloseTo(-max, 12);
    const [narrowMin, narrowMax] = yAxisRange(0.5, 1);
    expect(narrowMin).toBeCloseTo(-0.512, 9);
    expect(narrowMax).toBeCloseTo(0.512, 9);
  });

  it("formats V/div readouts in volts and millivolts", () => {
    expect(formatVDiv(5)).toBe("5 В/дел");
    expect(formatVDiv(50)).toBe("50 В/дел");
    expect(formatVDiv(0.5)).toBe("500 мВ/дел");
  });
});
