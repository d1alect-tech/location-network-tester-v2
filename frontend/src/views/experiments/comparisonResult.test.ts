import { beforeEach, describe, expect, it } from "vitest";
import type {
  ComparabilityReport,
  StatisticsMetadata,
  StatisticsResultEnvelope,
} from "../../api/types-research";
import type { ComparisonResultTarget } from "./comparisonResult";
import { renderEnvelope, renderReport, showBanner } from "./comparisonResult";
import type { EffectView } from "./resultPanel";

const META: StatisticsMetadata = {
  units: "В²/Гц",
  sampling_unit: "session",
  hierarchy: ["session"],
  n: 8,
  missing_count: 0,
  exclusions: [],
  estimator: "hodges_lehmann",
  interval_method: "bootstrap",
  provenance: { experiment_id: "exp-1", experiment_revision: 2, estimand: "feat" },
};

function stubParse(raw: unknown): EffectView | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  const { mean_effect: mean, median_effect: median, robust_effect: robust } = record;
  if (typeof mean !== "number" || typeof median !== "number" || typeof robust !== "number")
    return null;
  const interval = record.interval;
  const low =
    typeof interval === "object" && interval !== null
      ? ((interval as Record<string, unknown>).low ?? null)
      : null;
  const high =
    typeof interval === "object" && interval !== null
      ? ((interval as Record<string, unknown>).high ?? null)
      : null;
  return {
    mean,
    median,
    robust,
    intervalLow: typeof low === "number" ? low : null,
    intervalHigh: typeof high === "number" ? high : null,
  };
}

function mountTarget(): { root: HTMLElement; resultHost: HTMLElement } {
  const root = document.createElement("section");
  const resultHost = document.createElement("div");
  root.append(resultHost);
  document.body.append(root);
  return { root, resultHost };
}

function mountV6Target(): ComparisonResultTarget {
  const base = mountTarget();
  const gateHost = document.createElement("div");
  gateHost.className = "comparability-gate";
  gateHost.setAttribute("data-state", "unknown");
  base.root.prepend(gateHost);
  return { ...base, gateHost, bannerClass: "banner banner-inline" };
}

describe("comparisonResult: renderReport", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("blocked report renders gate banner with exact reason", () => {
    const target = mountTarget();
    const report: ComparabilityReport = {
      comparable: false,
      findings: [{ level: "block", code: "mixed_types", dimension: "modality", fields: ["ch2"] }],
    };
    renderReport(target, report);
    expect(target.resultHost.textContent).toContain(
      "Сравнение заблокировано проверкой сравнимости.",
    );
    expect(target.resultHost.textContent).toContain("mixed_types");
    expect(target.resultHost.textContent).toContain(
      "Точная причина: mixed_types. Числовой расчёт запрещён до устранения.",
    );
  });

  it("comparable report shows confirmation banner before host", () => {
    const target = mountTarget();
    renderReport(target, { comparable: true, findings: [] });
    const banner = target.root.querySelector(".lnt-exp-compare-status");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("Сравнимость подтверждена");
  });
});

describe("comparisonResult: renderEnvelope", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("refusal envelope renders blocked contrast panel", () => {
    const target = mountTarget();
    const envelope: StatisticsResultEnvelope = {
      result_kind: "refusal",
      result: { reason_code: "drift_a" },
      metadata: META,
    };
    renderEnvelope(target, envelope, stubParse);
    expect(target.resultHost.textContent).toContain("Результат сравнения");
    expect(target.resultHost.textContent).toContain("Контраст заблокирован");
  });

  it("effect envelope renders comparison result with values", () => {
    const target = mountTarget();
    const envelope: StatisticsResultEnvelope = {
      result_kind: "effect",
      result: {
        effect: {
          mean_effect: 1.5,
          median_effect: 1.25,
          robust_effect: 1.4,
          interval: { low: 0.5, high: 2.5 },
        },
      },
      metadata: META,
    };
    renderEnvelope(target, envelope, stubParse);
    expect(target.resultHost.textContent).toContain("Результат сравнения");
    expect(target.resultHost.textContent).toContain("1.5000");
  });

  it("descriptive envelope renders no-interval panel", () => {
    const target = mountTarget();
    const envelope: StatisticsResultEnvelope = {
      result_kind: "descriptive",
      result: {
        mean_effect: 0.75,
        median_effect: 0.5,
        robust_effect: 0.6,
        interval: null,
      },
      metadata: META,
    };
    renderEnvelope(target, envelope, stubParse);
    expect(target.resultHost.textContent).toContain("Описательный результат (без интервала)");
  });
});

describe("comparisonResult: showBanner", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("error banner uses alert role, ok uses status, and rerender replaces", () => {
    const target = mountTarget();
    showBanner(target, "первое", "ok");
    showBanner(target, "второе", "error");
    const banners = target.root.querySelectorAll(".lnt-exp-compare-status");
    expect(banners.length).toBe(1);
    expect(banners[0]?.textContent).toBe("второе");
    expect(banners[0]?.getAttribute("role")).toBe("alert");
    expect(banners[0]?.className).toContain("lnt-exp-banner-error");
  });

  it("bannerClass appends V6 token classes without dropping the marker class", () => {
    const target = mountV6Target();
    showBanner(target, "токены", "ok");
    const banner = target.root.querySelector(".lnt-exp-compare-status");
    expect(banner?.className).toContain("banner banner-inline");
    expect(banner?.className).toContain("lnt-exp-banner-ok");
  });
});

describe("comparisonResult: гейт сравнимости (V6 .comparability-gate)", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("blocked report drives the gate host to data-state=blocked with the exact reason", () => {
    const target = mountV6Target();
    renderReport(target, {
      comparable: false,
      findings: [{ level: "block", code: "mixed_types", dimension: "modality", fields: ["ch2"] }],
    });
    expect(target.gateHost?.getAttribute("data-state")).toBe("blocked");
    expect(target.gateHost?.textContent).toBe(
      "Сравнение заблокировано проверкой сравнимости. Точная причина: mixed_types. " +
        "Числовой расчёт запрещён до устранения.",
    );
  });

  it("comparable report drives the gate host to data-state=ok with the finding count", () => {
    const target = mountV6Target();
    renderReport(target, {
      comparable: true,
      findings: [{ level: "info", code: "same_device", dimension: "hardware", fields: [] }],
    });
    expect(target.gateHost?.getAttribute("data-state")).toBe("ok");
    expect(target.gateHost?.textContent).toBe(
      "Сравнимость подтверждена (1 измерений без блокировок). Можно запускать расчёт.",
    );
  });
});
