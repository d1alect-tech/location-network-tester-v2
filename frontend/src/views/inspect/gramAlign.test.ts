import { describe, expect, it } from "vitest";
import type { SpectrogramLevel } from "../../components/charts/spectrogramModel";
import { alignGramLevels } from "./gramAlign";

function makeLevel(
  timeS: readonly number[],
  frequencyHz: readonly number[],
  powerDb: readonly number[],
): SpectrogramLevel {
  return {
    timeS: Float64Array.from(timeS),
    frequencyHz: Float64Array.from(frequencyHz),
    powerDb: Float32Array.from(powerDb),
    timeBins: timeS.length,
    bands: frequencyHz.length,
  };
}

describe("alignGramLevels", () => {
  it("returns per-cell dB delta when grids match", () => {
    // Given: 2 time × 3 freq, known power already in dB
    const a = makeLevel([0, 0.5], [10, 20, 30], [1, 2, 3, 4, 5, 6]);
    const b = makeLevel([0, 0.5], [10, 20, 30], [3, 5, 8, 10, 12, 15]);

    // When
    const result = alignGramLevels(a, b);

    // Then: delta is B − A in dB, not 10·log10
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(Array.from(result.delta)).toEqual([2, 3, 5, 6, 7, 9]);
  });

  it("returns grid_mismatch when timeS lengths differ", () => {
    // Given
    const a = makeLevel([0, 0.5], [10, 20, 30], [1, 2, 3, 4, 5, 6]);
    const b = makeLevel([0, 0.5, 1], [10, 20, 30], [1, 2, 3, 4, 5, 6, 7, 8, 9]);

    // When / Then: no throw
    expect(() => alignGramLevels(a, b)).not.toThrow();
    expect(alignGramLevels(a, b)).toEqual({ kind: "mismatch", code: "grid_mismatch" });
  });

  it("returns grid_mismatch when a frequencyHz value differs", () => {
    // Given: same lengths, one frequency bin off
    const a = makeLevel([0, 0.5], [10, 20, 30], [1, 2, 3, 4, 5, 6]);
    const b = makeLevel([0, 0.5], [10, 21, 30], [1, 2, 3, 4, 5, 6]);

    // When / Then
    expect(() => alignGramLevels(a, b)).not.toThrow();
    expect(alignGramLevels(a, b)).toEqual({ kind: "mismatch", code: "grid_mismatch" });
  });
});
