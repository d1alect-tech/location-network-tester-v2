import { beforeEach, describe, expect, it } from "vitest";
import type { LntApiClient } from "../../api/client";
import { ComparisonView } from "./comparisonView";

function stubClient(): Pick<LntApiClient, "research" | "statistics"> {
  return {
    research: {},
    statistics: {},
  } as unknown as Pick<LntApiClient, "research" | "statistics">;
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
});
