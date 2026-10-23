import { describe, expect, it } from "vitest";
import { ADAPTER_PRESET, analysisFloorSeconds, settlingSeconds } from "./adapterPreset";

describe("ADAPTER_PRESET — закреплённое зеркало lnt.ripple.adapter", () => {
  it("фиксирует номиналы x1 series-C адаптера", () => {
    expect(ADAPTER_PRESET).toEqual({
      capNfNominal: 100,
      seriesROhmNominal: 0,
      probeMultiplier: 1,
      rinOhm: 1_000_000,
      settlingTauMultiple: 10,
      topologyId: "series_c_at_dut_tip_x1_v1",
    });
  });
});

describe("settlingSeconds — номинальная политика 10τ", () => {
  it("100 нФ, 0 Ом даёт ровно 1.0 с", () => {
    expect(settlingSeconds(100, 0)).toBe(1);
  });

  it("растёт с ёмкостью: 1000 нФ даёт ровно 10.0 с", () => {
    expect(settlingSeconds(1000, 0)).toBe(10);
  });
});

describe("analysisFloorSeconds — пол анализа (settle + nperseg)", () => {
  it("floor(100, 0, 8e6) === 2.0", () => {
    expect(analysisFloorSeconds(100, 0, 8_000_000)).toBe(2);
  });

  it("floor(1000, 0, 8e6) === 11.0", () => {
    expect(analysisFloorSeconds(1000, 0, 8_000_000)).toBe(11);
  });
});
