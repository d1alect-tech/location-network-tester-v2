import { beforeEach, describe, expect, it, vi } from "vitest";
import { wireInspectV6Gram } from "./inspectV6Gram";

const loadState = vi.hoisted(() => ({ releases: [] as Array<() => void> }));

vi.mock("./gramPair", () => ({
  createGramPair: () => ({
    load: () =>
      new Promise<void>((resolve) => {
        loadState.releases.push(resolve);
      }),
    setMode() {},
    mode: () => "a",
    setDetector() {},
    detector: () => "mean",
    holdAvailable: () => false,
    gridMatches: () => false,
    paired: () => false,
    empty: () => true,
    current: () => ({ kind: "mismatch" }),
    dispose() {},
  }),
}));

describe("wireInspectV6Gram request generation", () => {
  beforeEach(() => {
    loadState.releases.length = 0;
  });

  it("does not paint an older refresh while the current pair is loading", async () => {
    const gramHost = document.createElement("div");
    const gramBar = document.createElement("div");
    const gram = wireInspectV6Gram({
      client: { analysis: { artifactBytes: async () => new ArrayBuffer(0) } },
      spectrumPanel: { gramHost, gramBar },
    });
    const old = gram.refresh("old", null);
    const current = gram.refresh("current", null);

    loadState.releases[0]?.();
    await old;

    expect(gramBar.querySelector(".gram-scale")?.textContent).toBe("");
    expect(gramBar.querySelector<HTMLButtonElement>(".gram-mode")?.disabled).toBe(false);

    loadState.releases[1]?.();
    await current;
    expect(gramBar.querySelector(".gram-scale")?.textContent).toContain("нет спектрограммы");
  });
});
