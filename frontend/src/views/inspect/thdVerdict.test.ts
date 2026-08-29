import { describe, expect, it } from "vitest";
import { THD_V_LIMIT, thdVerdict } from "./thdVerdict";

/** Given / When / Then: THD-V badge vs 0.08. Never treats a missing file as 0. */

describe("thdVerdict", () => {
  it("fails when mean window THD is above the limit and cycles are enough", () => {
    // Given: two windows whose mean exceeds 0.08, 118 cycles (fixture shape).
    const input = {
      windows: [{ thd: 0.09 }, { thd: 0.11 }],
      cyclesAnalyzed: 118,
      harmonicsFailed: false,
    };

    // When
    const verdict = thdVerdict(input);

    // Then
    expect(THD_V_LIMIT).toBe(0.08);
    expect(verdict.kind).toBe("fail");
    expect(verdict.meanThd).toBeCloseTo(0.1);
  });

  it("passes when mean window THD is at or below the limit and cycles are enough", () => {
    // Given
    const input = {
      windows: [{ thd: 0.04 }, { thd: 0.04 }],
      cyclesAnalyzed: 100,
      harmonicsFailed: false,
    };

    // When
    const verdict = thdVerdict(input);

    // Then
    expect(verdict.kind).toBe("pass");
    expect(verdict.meanThd).toBeCloseTo(0.04);
  });

  it("hides the badge when cycles_analyzed is below 100", () => {
    // Given: THD would fail, but the cycle gate forbids a badge.
    const input = {
      windows: [{ thd: 0.2 }],
      cyclesAnalyzed: 99,
      harmonicsFailed: false,
    };

    // When
    const verdict = thdVerdict(input);

    // Then
    expect(verdict.kind).toBe("hidden");
    expect(verdict.meanThd).toBeCloseTo(0.2);
  });

  it("returns legacy when harmonics windows are absent — never a fake 0 pass", () => {
    // Given: no harmonics.json windows
    const input = {
      windows: null,
      cyclesAnalyzed: 118,
      harmonicsFailed: false,
    };

    // When
    const verdict = thdVerdict(input);

    // Then
    expect(verdict.kind).toBe("legacy");
    expect(verdict.meanThd).toBeNull();
  });

  it("hides the badge when the harmonics branch failed", () => {
    // Given
    const input = {
      windows: [{ thd: 0.01 }],
      cyclesAnalyzed: 200,
      harmonicsFailed: true,
    };

    // When
    const verdict = thdVerdict(input);

    // Then
    expect(verdict.kind).toBe("hidden");
  });
});
