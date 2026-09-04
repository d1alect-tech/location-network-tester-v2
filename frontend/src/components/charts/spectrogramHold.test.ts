import { describe, expect, it } from "vitest";
import { levelFromNpz } from "./spectrogramSetup";

function arrays(
  entries: Record<string, { data: ArrayBuffer }>,
): Map<string, { data: ArrayBuffer }> {
  return new Map(Object.entries(entries));
}

function f64(values: readonly number[]): { data: ArrayBuffer } {
  return { data: Float64Array.from(values).buffer as ArrayBuffer };
}

function f32(values: readonly number[]): { data: ArrayBuffer } {
  return { data: Float32Array.from(values).buffer as ArrayBuffer };
}

describe("levelFromNpz: max-hold след (очередь B2)", () => {
  it("читает power_max_hold_db рядом с mean", () => {
    const level = levelFromNpz(
      arrays({
        time_s: f64([0, 0.5]),
        frequency_hz: f64([10, 20]),
        power_db: f32([0, 2, 4, 6]),
        power_max_hold_db: f32([9, 8, 7, 6]),
      }),
    );

    expect(Array.from(level.powerDb)).toEqual([0, 2, 4, 6]);
    expect(level.powerMaxHoldDb).toBeDefined();
    expect(Array.from(level.powerMaxHoldDb ?? [])).toEqual([9, 8, 7, 6]);
  });

  it("без hold-ключа след отсутствует, mean цел", () => {
    const level = levelFromNpz(
      arrays({
        time_s: f64([0, 0.5]),
        frequency_hz: f64([10, 20]),
        power_db: f32([0, 2, 4, 6]),
      }),
    );

    expect(level.powerMaxHoldDb).toBeUndefined();
    expect(Array.from(level.powerDb)).toEqual([0, 2, 4, 6]);
  });

  it("hold неверной длины отбрасывается", () => {
    const level = levelFromNpz(
      arrays({
        time_s: f64([0, 0.5]),
        frequency_hz: f64([10, 20]),
        power_db: f32([0, 2, 4, 6]),
        power_max_hold_db: f32([1, 2]),
      }),
    );

    expect(level.powerMaxHoldDb).toBeUndefined();
  });
});
