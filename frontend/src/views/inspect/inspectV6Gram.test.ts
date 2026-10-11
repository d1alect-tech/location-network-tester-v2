import { beforeEach, describe, expect, it, vi } from "vitest";
import { createGramSection } from "./inspectV6Gram";

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

describe("createGramSection request generation", () => {
  beforeEach(() => {
    loadState.releases.length = 0;
  });

  it("does not paint an older refresh while the current pair is loading", async () => {
    const toolbarHost = document.createElement("div");
    const canvasHost = document.createElement("div");
    const gram = createGramSection({
      client: { analysis: { artifactBytes: async () => new ArrayBuffer(0) } },
      toolbarHost,
      canvasHost,
    });
    const old = gram.refresh("old", null);
    const current = gram.refresh("current", null);

    loadState.releases[0]?.();
    await old;

    expect(toolbarHost.querySelector(".gram-scale")?.textContent).toBe("");
    expect(toolbarHost.querySelector<HTMLButtonElement>(".gram-mode")?.disabled).toBe(false);

    loadState.releases[1]?.();
    await current;
    expect(toolbarHost.querySelector(".gram-scale")?.textContent).toContain("нет спектрограммы");
  });

  it("owns its DOM: controls land in the toolbar host, canvas in the canvas host", () => {
    const toolbarHost = document.createElement("div");
    const canvasHost = document.createElement("div");
    createGramSection({
      client: { analysis: { artifactBytes: async () => new ArrayBuffer(0) } },
      toolbarHost,
      canvasHost,
    });

    expect(toolbarHost.querySelector("[data-spectrogram-mode]")).toBeInstanceOf(HTMLButtonElement);
    expect(toolbarHost.querySelector("[data-spectrogram-detector]")).toBeInstanceOf(
      HTMLButtonElement,
    );
    expect(canvasHost.querySelector(".lnt-spec-chart")).toBeInstanceOf(HTMLElement);
  });
});
