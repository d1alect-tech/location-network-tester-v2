/** Подписи оси частоты: короткий формат держит ось X читаемой при шаге
 *  uPlot 50–64 px («4,000,000» шире шага и слипается с соседями). */

import { describe, expect, it } from "vitest";
import { formatFrequencyTick } from "./saUnits";

describe("деления оси частоты", () => {
  it("кГц и МГц без хвостовых нулей, Гц — целые", () => {
    expect(formatFrequencyTick(0)).toBe("0 Гц");
    expect(formatFrequencyTick(250_000)).toBe("250 кГц");
    expect(formatFrequencyTick(500_000)).toBe("500 кГц");
    expect(formatFrequencyTick(750_000)).toBe("750 кГц");
    expect(formatFrequencyTick(1_000_000)).toBe("1 МГц");
    expect(formatFrequencyTick(1_250_000)).toBe("1,25 МГц");
    expect(formatFrequencyTick(4_000_000)).toBe("4 МГц");
    expect(formatFrequencyTick(10_000)).toBe("10 кГц");
  });

  it("мусор и отрицательные значения не ломают подпись", () => {
    expect(formatFrequencyTick(Number.NaN)).toBe("");
    expect(formatFrequencyTick(-250_000)).toBe("-250 кГц");
  });
});
