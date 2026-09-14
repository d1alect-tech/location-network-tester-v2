import { describe, expect, it } from "vitest";
import { parseCharacterizationSummary } from "./extendedRun";

describe("parseCharacterizationSummary", () => {
  it("reads F01 f1_hz and all 18 family statuses", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: index === 0 ? "f01_phase_cycle" : `f${String(index + 1).padStart(2, "0")}_other`,
        status: index === 0 ? "available" : "unavailable",
        comparison_summary:
          index === 0 ? [{ name: "f1_hz", value: 50.01, unit: "Hz", circular: false }] : [],
      })),
    };

    const summary = parseCharacterizationSummary(payload);

    expect(summary?.f1Hz).toBeCloseTo(50.01, 5);
    expect(summary?.families).toHaveLength(18);
    expect(summary?.families[0]).toEqual({ id: "f01_phase_cycle", status: "available" });
  });

  it("rejects bundles without exactly 18 families", () => {
    expect(parseCharacterizationSummary({ families: [] })).toBeNull();
    expect(parseCharacterizationSummary(null)).toBeNull();
  });

  it("reports null F01 when the summary carries no f1_hz", () => {
    const payload = {
      families: Array.from({ length: 18 }, (_, index) => ({
        family_id: `f${String(index + 1).padStart(2, "0")}`,
        status: "unavailable",
        comparison_summary: [],
      })),
    };

    expect(parseCharacterizationSummary(payload)?.f1Hz).toBeNull();
  });
});
