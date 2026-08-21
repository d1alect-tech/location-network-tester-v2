import { beforeEach, describe, expect, it } from "vitest";
import { createSplitPane } from "./splitpane";

describe("createSplitPane", () => {
  beforeEach(() => {
    document.body.textContent = "";
    window.localStorage.clear();
  });

  function makePane(storageKey?: string): ReturnType<typeof createSplitPane> {
    const left = document.createElement("div");
    const right = document.createElement("div");
    const pane = createSplitPane(left, right, { initialRatio: 50, storageKey });
    document.body.append(pane.root); // фокус в jsdom работает только на подключённых узлах
    return pane;
  }

  it("renders a keyboard-focusable separator with aria semantics", () => {
    const pane = makePane();
    const sep = pane.root.querySelector('[role="separator"]') as HTMLElement;
    expect(sep).not.toBeNull();
    expect(sep.getAttribute("aria-orientation")).toBe("vertical");
    expect(sep.getAttribute("aria-valuenow")).toBe("50");
    expect(sep.tabIndex).toBe(0);
  });

  it("ArrowRight/ArrowLeft adjust ratio by step and update aria-valuenow", () => {
    const pane = makePane();
    const sep = pane.root.querySelector('[role="separator"]') as HTMLElement;
    sep.focus();
    sep.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(pane.getRatio()).toBe(55);
    expect(sep.getAttribute("aria-valuenow")).toBe("55");
    sep.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
    expect(pane.getRatio()).toBe(50);
  });

  it("clamps ratio to [20, 80]", () => {
    const pane = makePane();
    const sep = pane.root.querySelector('[role="separator"]') as HTMLElement;
    for (let i = 0; i < 20; i += 1) {
      sep.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    }
    expect(pane.getRatio()).toBeLessThanOrEqual(80);
  });

  it("persists the ratio and restores it on next construction", () => {
    const pane = makePane("lnt-split-test");
    const sep = pane.root.querySelector('[role="separator"]') as HTMLElement;
    sep.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(window.localStorage.getItem("lnt-split-test")).toBe("55");

    const restored = makePane("lnt-split-test");
    expect(restored.getRatio()).toBe(55);
  });
});
