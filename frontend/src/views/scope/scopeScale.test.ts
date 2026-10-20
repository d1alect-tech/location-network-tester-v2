/** Todo 8 + директива владельца 2026-10-19: лестница В/дел до 10 мВ/дел,
 * окно оси = ±4·В/дел·probe (8 делений экрана), закон raw→V не изменился.
 * Младшие шаги — экранное усиление: vdivTagText честно называет вход АЦП. */

import { describe, expect, it } from "vitest";
import {
  ADC_CENTER,
  DEFAULT_SCOPE_SETTINGS,
  PROBE_STEPS,
  SCREEN_DIVISIONS,
  VDIV_STEPS,
  effectiveVDiv,
  formatVDiv,
  formatVolts,
  halfSpanVolts,
  hardwareRangeFor,
  rangeCodeOf,
  rawToVolts,
  vdivTagText,
  voltsPerLsb,
  windowHalfVolts,
  yAxisRange,
} from "./scopeScale";

describe("scale law of the live sweep (Todo 8, owner directive 2026-10-19)", () => {
  it("V/div ladder runs 5 V..10 mV in 1-2-5 steps", () => {
    expect(VDIV_STEPS).toEqual([5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01]);
    expect(DEFAULT_SCOPE_SETTINGS.vDiv).toBe(1);
    expect(DEFAULT_SCOPE_SETTINGS.probe).toBe(1);
    expect(DEFAULT_SCOPE_SETTINGS.groundCh1V).toBe(0);
    expect(DEFAULT_SCOPE_SETTINGS.groundCh2V).toBe(0);
  });

  it("raw→V follows 5.12·probe/(code<<7) on each verified code", () => {
    expect(rangeCodeOf(5)).toBe(1);
    expect(rangeCodeOf(1)).toBe(5);
    expect(rangeCodeOf(0.5)).toBe(10);
    // Шаги экрана вне АЦП-таблицы — не коды гейна (закон ниже на кодах).
    expect(() => rangeCodeOf(0.2)).toThrow();
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

  it("y window is ±4·V/div·probe — eight screen divisions", () => {
    expect(SCREEN_DIVISIONS).toBe(8);
    expect(windowHalfVolts(1, 1)).toBeCloseTo(4, 12);
    const [min, max] = yAxisRange(0.01, 1);
    expect(min).toBeCloseTo(-0.04, 12);
    expect(max).toBeCloseTo(0.04, 12);
    const [probeMin, probeMax] = yAxisRange(0.01, 10);
    expect(probeMin).toBeCloseTo(-0.4, 12);
    expect(probeMax).toBeCloseTo(0.4, 12);
  });

  it("hardware range picks the tightst code that fits the window", () => {
    expect(hardwareRangeFor(5)).toBe(5);
    expect(hardwareRangeFor(2)).toBe(5);
    expect(hardwareRangeFor(1)).toBe(5);
    expect(hardwareRangeFor(0.5)).toBe(5);
    expect(hardwareRangeFor(0.2)).toBe(1);
    expect(hardwareRangeFor(0.1)).toBe(0.5);
    expect(hardwareRangeFor(0.05)).toBe(0.5);
    expect(hardwareRangeFor(0.02)).toBe(0.5);
    expect(hardwareRangeFor(0.01)).toBe(0.5);
  });

  it("honesty tag: screen gain below the ADC floor, dead space above", () => {
    expect(vdivTagText(1, 1)).toBeNull();
    expect(vdivTagText(0.2, 1)).toBeNull();
    expect(vdivTagText(0.1, 1)).toBeNull();
    expect(vdivTagText(5, 1)).toContain("сетка шире входа АЦП");
    expect(vdivTagText(2, 1)).toContain("сетка шире входа АЦП");
    expect(vdivTagText(0.5, 1)).toContain("экранное усиление");
    expect(vdivTagText(0.01, 1)).toContain("×12.8");
    expect(vdivTagText(0.01, 1)).toContain("±512 мВ");
    // Пробник масштабирует и окно, и вход — ярлык честен при ×10.
    expect(vdivTagText(0.01, 10)).toContain("×12.8");
    expect(vdivTagText(0.01, 10)).toContain("±5.12 В");
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

  it("formats V/div and volts readouts in volts and millivolts", () => {
    expect(formatVDiv(5)).toBe("5 В/дел");
    expect(formatVDiv(50)).toBe("50 В/дел");
    expect(formatVDiv(0.5)).toBe("500 мВ/дел");
    expect(formatVDiv(0.01)).toBe("10 мВ/дел");
    expect(formatVolts(5.12)).toBe("5.12 В");
    expect(formatVolts(0.512)).toBe("512 мВ");
  });
});
