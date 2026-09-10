import { describe, expect, it } from "vitest";
import type { SessionDetailPayload } from "../../api/types-plots";
import { metricValue } from "./experimentsSync";

function detail(analysis: Record<string, unknown>): SessionDetailPayload {
  return { analysis } as SessionDetailPayload;
}

describe("metricValue", () => {
  it("uses the shared shipped metric contract", () => {
    expect(metricValue(detail({ needle: { needle_mean_v: 0.125 } }), "needle_mean_v")).toBe(0.125);
    expect(
      metricValue(detail({ line_quality: { thd_ratio: 0.03 } }), "line_quality.thd_ratio"),
    ).toBe(0.03);
    expect(metricValue(detail({ metrics: { legacy: 2.5 } }), "legacy")).toBe(2.5);
  });

  it("rejects non-finite and unrelated nested values", () => {
    expect(
      metricValue(detail({ needle: { needle_mean_v: Number.NaN } }), "needle_mean_v"),
    ).toBeNull();
    expect(metricValue(detail({ direct: Number.POSITIVE_INFINITY }), "direct")).toBeNull();
    expect(metricValue(detail({ unrelated: { needle_mean_v: 9 } }), "needle_mean_v")).toBeNull();
  });
});
