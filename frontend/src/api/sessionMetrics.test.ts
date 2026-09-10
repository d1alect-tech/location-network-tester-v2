import { describe, expect, it } from "vitest";
import { knownMetricUnits, sessionMetricValue } from "./sessionMetrics";

describe("knownMetricUnits", () => {
  it("returns the persisted scalar unit without converting the value", () => {
    expect(knownMetricUnits("needle_mean_v")).toBe("V");
    expect(knownMetricUnits("needle.sync_power_v2")).toBe("V^2");
    expect(knownMetricUnits("line_quality.fundamental_hz")).toBe("Hz");
    expect(knownMetricUnits("async_sync_ratio")).toBe("dimensionless");
    expect(knownMetricUnits("cycles_analyzed")).toBe("dimensionless");
  });

  it("requires an explicit unit for an unknown metric", () => {
    expect(knownMetricUnits("custom_metric")).toBeNull();
  });
});

describe("sessionMetricValue", () => {
  it("reads persisted needle metrics from the literal analysis payload", () => {
    const detail = {
      analysis: {
        needle: { needle_mean_v: 0.125, async_sync_ratio: 1.75 },
        line_quality: null,
      },
    };

    expect(sessionMetricValue(detail, "needle_mean_v")).toBe(0.125);
    expect(sessionMetricValue(detail, "needle.async_sync_ratio")).toBe(1.75);
  });

  it("reads persisted line-quality metrics without transforming their units", () => {
    const detail = {
      analysis: {
        needle: null,
        line_quality: {
          fundamental_rms_v: 229.4,
          thd_ratio: 0.037,
          crest_factor: 1.42,
        },
      },
    };

    expect(sessionMetricValue(detail, "fundamental_rms_v")).toBe(229.4);
    expect(sessionMetricValue(detail, "line_quality.thd_ratio")).toBe(0.037);
  });

  it("keeps shipped direct and metrics shapes but rejects non-finite values", () => {
    expect(sessionMetricValue({ analysis: { metrics: { legacy: 3.5 } } }, "legacy")).toBe(3.5);
    expect(sessionMetricValue({ analysis: { direct: 4.5 } }, "direct")).toBe(4.5);
    expect(
      sessionMetricValue({ analysis: { needle: { needle_mean_v: Number.NaN } } }, "needle_mean_v"),
    ).toBeNull();
    expect(
      sessionMetricValue(
        { analysis: { line_quality: { thd_ratio: Number.POSITIVE_INFINITY } } },
        "thd_ratio",
      ),
    ).toBeNull();
    expect(
      sessionMetricValue({ analysis: { unrelated: { needle_mean_v: 9 } } }, "needle_mean_v"),
    ).toBeNull();
  });
});
