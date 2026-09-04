import { describe, expect, it } from "vitest";
import { peakDeltas, type PeakDelta, type PeakFrequency } from "./peaksDelta";

describe("peakDeltas", () => {
  it("calculates deltaDb and preserves frequencyHz for matching peaks", () => {
    // Given
    const freq: readonly number[] = [10, 100, 1000];
    const psdA: readonly number[] = [1e-6, 1e-4, 1e-2];
    const psdB: readonly number[] = [1e-6, 1e-4, 1e-3];
    const peaks: readonly PeakFrequency[] = [{ frequencyHz: 1000 }];

    // When
    const result: readonly PeakDelta[] = peakDeltas(freq, psdA, psdB, peaks);

    // Then
    expect(result).toHaveLength(1);
    expect(result[0]?.frequencyHz).toBe(1000);
    const expectedDeltaDb = 10 * Math.log10(1e-3 / 1e-2); // -10 dB
    expect(result[0]?.deltaDb).not.toBeNull();
    expect(Math.abs((result[0]?.deltaDb ?? 0) - expectedDeltaDb)).toBeLessThan(1e-9);
  });

  it("finds the nearest frequency bin by absolute frequency distance", () => {
    // Given
    const freq: readonly number[] = [10, 100, 1000];
    const psdA: readonly number[] = [1e-6, 1e-4, 1e-2];
    const psdB: readonly number[] = [1e-6, 1e-3, 1e-3];
    const peaks: readonly PeakFrequency[] = [{ frequencyHz: 90 }]; // Nearest to 100 (diff 10 vs 80 vs 910)

    // When
    const result: readonly PeakDelta[] = peakDeltas(freq, psdA, psdB, peaks);

    // Then
    expect(result).toHaveLength(1);
    expect(result[0]?.frequencyHz).toBe(90);
    const expectedDeltaDb = 10 * Math.log10(1e-3 / 1e-4); // 10 dB
    expect(result[0]?.deltaDb).not.toBeNull();
    expect(Math.abs((result[0]?.deltaDb ?? 0) - expectedDeltaDb)).toBeLessThan(1e-9);
  });

  it("returns null deltaDb when psdA is <= 0 or missing or non-finite", () => {
    // Given
    const freq: readonly number[] = [10, 100, 1000];
    const psdA: readonly number[] = [0, -1, 1e-4];
    const psdB: readonly number[] = [1e-6, 1e-4, 0];
    const peaks: readonly PeakFrequency[] = [
      { frequencyHz: 10 },
      { frequencyHz: 100 },
      { frequencyHz: 1000 },
      { frequencyHz: 5000 },
    ];

    // When
    const result: readonly PeakDelta[] = peakDeltas(freq, psdA, psdB, peaks);

    // Then
    expect(result).toHaveLength(4);
    expect(result[0]?.deltaDb).toBeNull(); // psdA is 0
    expect(result[1]?.deltaDb).toBeNull(); // psdA is negative
    expect(result[2]?.deltaDb).toBeNull(); // psdB is 0
    expect(result[3]?.deltaDb).toBeNull(); // psdB is 0 (nearest to 1000)
  });

  it("returns an empty array when peaks is empty", () => {
    // Given
    const freq: readonly number[] = [10, 100, 1000];
    const psdA: readonly number[] = [1e-6, 1e-4, 1e-2];
    const psdB: readonly number[] = [1e-6, 1e-4, 1e-3];
    const peaks: readonly PeakFrequency[] = [];

    // When
    const result: readonly PeakDelta[] = peakDeltas(freq, psdA, psdB, peaks);

    // Then
    expect(result).toEqual([]);
  });
});
