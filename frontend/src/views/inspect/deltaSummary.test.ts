import { describe, expect, it } from "vitest";
import { formatDeltaDb, summarizeDelta } from "./deltaSummary";

describe("summarizeDelta", () => {
  it("считает среднее и максимум модуля по валидным бинам", () => {
    const summary = summarizeDelta([1, 1, 1], [1, 10, 100]);
    expect(summary?.bins).toBe(3);
    expect(summary?.meanDb).toBeCloseTo(10, 10);
    expect(summary?.maxAbsDb).toBeCloseTo(20, 10);
  });

  it("пропускает мусор, пустой итог — null", () => {
    expect(summarizeDelta([1, 0, -2, Number.NaN], [1, 1, 1, 1])?.bins).toBe(1);
    expect(summarizeDelta([0], [0])).toBeNull();
    expect(summarizeDelta(null, [1])).toBeNull();
    expect(summarizeDelta([1], null)).toBeNull();
    expect(summarizeDelta([], [])).toBeNull();
  });

  it("идёт по короткой сетке", () => {
    expect(summarizeDelta([1, 1, 1], [10])?.bins).toBe(1);
  });
});

describe("formatDeltaDb", () => {
  it("знак всегда, запятая по-русски", () => {
    expect(formatDeltaDb(0.34)).toBe("+0,3 дБ");
    // Node ставит дефис-минус, браузер — − (U+2212); число и запятая те же.
    expect(formatDeltaDb(-1.25)).toBe("-1,3 дБ");
    expect(formatDeltaDb(0)).toBe("0,0 дБ");
  });
});
