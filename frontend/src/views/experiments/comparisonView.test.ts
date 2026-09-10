import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import { ComparisonView } from "./comparisonView";
import type { ExperimentDetail } from "./experimentsStore";
import { proposeMember } from "./memberQc";
import type { MemberRow } from "./memberTableView";

function stubClient(): Pick<LntApiClient, "research" | "statistics"> {
  return {
    research: {},
    statistics: {},
  } as unknown as Pick<LntApiClient, "research" | "statistics">;
}

function detail(experimentId: string, featureKey: string): ExperimentDetail {
  return {
    experiment: {
      experiment_id: experimentId,
      protocol: { kind: "ab" },
      primary_estimands: [{ feature_key: featureKey }],
      steps: [
        { order: 1, condition_id: "cond_a" },
        { order: 2, condition_id: "cond_b" },
      ],
    },
    members: [],
    steps: [],
  } as unknown as ExperimentDetail;
}

function rows(): MemberRow[] {
  return [
    {
      sessionId: "a1",
      role: "cond_a:a1",
      conditionId: "cond_a",
      order: 1,
      health: "ok",
      verdict: { tone: "ok", label: "ok", recommended_state: null, reason_code: null },
      inclusion: proposeMember("a1", "test", "init"),
    },
    {
      sessionId: "b1",
      role: "cond_b:b1",
      conditionId: "cond_b",
      order: 2,
      health: "ok",
      verdict: { tone: "ok", label: "ok", recommended_state: null, reason_code: null },
      inclusion: proposeMember("b1", "test", "init"),
    },
  ];
}

describe("ComparisonView без контекста (U3: no-op → видимая причина)", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("check button shows a banner instead of a silent return", () => {
    const view = new ComparisonView({ client: stubClient(), valueSource: async () => null });
    document.body.append(view.root);

    const check = view.root.querySelector<HTMLButtonElement>("#lnt-exp-check-comparability");
    check?.click();

    const banner = view.root.querySelector(".lnt-exp-compare-status");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("эксперимент");
    view.abort();
  });

  it("run button shows a banner instead of a silent return", () => {
    const view = new ComparisonView({ client: stubClient(), valueSource: async () => null });
    document.body.append(view.root);

    const run = view.root.querySelector<HTMLButtonElement>("#lnt-exp-run-analysis");
    run?.click();

    const banner = view.root.querySelector(".lnt-exp-compare-status");
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain("эксперимент");
    view.abort();
  });

  it("defaults the known real metric to volts", () => {
    const view = new ComparisonView({ client: stubClient(), valueSource: async () => null });

    expect(view.root.querySelector<HTMLInputElement>("#lnt-exp-feature")?.value).toBe(
      "needle_mean_v",
    );
    expect(view.root.querySelector<HTMLInputElement>("#lnt-exp-units")?.value).toBe("V");
  });

  it("switches estimand and clears unknown units instead of retaining stale context", () => {
    const view = new ComparisonView({ client: stubClient(), valueSource: async () => null });
    view.setContext(detail("exp.first", "needle_mean_v"), rows());
    view.setContext(detail("exp.second", "unknown_metric"), rows());

    expect(view.root.querySelector<HTMLInputElement>("#lnt-exp-feature")?.value).toBe(
      "unknown_metric",
    );
    expect(view.root.querySelector<HTMLInputElement>("#lnt-exp-units")?.value).toBe("");
    expect(view.root.querySelector(".comparability-gate")?.getAttribute("data-state")).toBe(
      "unknown",
    );
  });

  it("does not reuse a comparable report after switching experiments", async () => {
    const submit = vi.fn();
    const client = {
      research: {
        comparabilityCheck: vi.fn().mockResolvedValue({ comparable: true, findings: [] }),
      },
      statistics: { submit },
    } as unknown as Pick<LntApiClient, "research" | "statistics">;
    const view = new ComparisonView({ client, valueSource: async () => 1 });
    document.body.append(view.root);
    view.setContext(detail("exp.first", "needle_mean_v"), rows());
    await view.runComparability();
    view.setContext(detail("exp.second", "needle_mean_v"), rows());

    await view.runAnalysis("needle_mean_v", "V", 43);

    expect(submit).not.toHaveBeenCalled();
    expect(view.root.querySelector(".lnt-exp-compare-status")?.textContent).toContain(
      "сравнимость не подтверждена",
    );
    view.abort();
  });
});
