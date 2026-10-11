import { describe, expect, it, vi } from "vitest";
import type { WaveformPayload } from "../../api/types-plots";
import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { createV6Extras } from "./v6Extras";
import type { V6ExtrasChrome } from "./v6Extras";

const WAVE: WaveformPayload = {
  channel: "ch1",
  time_s: [0, 1],
  voltage_v: [0.1, 0.2],
  point_count: 2,
};

function fakeChrome(): V6ExtrasChrome & { readonly sessions: Array<string | null> } {
  const bar = document.createElement("div");
  bar.className = "fake-w1-bar";
  const root = document.createElement("div");
  root.className = "fake-w1-chrome";
  const sessions: Array<string | null> = [];
  return {
    bar,
    root,
    sessions,
    setSession: (session) => {
      sessions.push(session);
    },
    onSummary: (publish) => {
      publish("панелей 0 · скаляров 0/4");
    },
    destroy: vi.fn(),
  };
}

function fakeViewFactory() {
  const renders: unknown[] = [];
  const createView = (options: UplotViewOptions): ChartHandle => {
    const root = document.createElement("div");
    options.container.append(root);
    return {
      root,
      render(request) {
        renders.push(request);
      },
      applyTheme() {},
      getData: () => null,
      destroy() {},
    };
  };
  return { createView, renders };
}

function setup() {
  const waveform = vi.fn().mockResolvedValue(WAVE);
  const chrome = fakeChrome();
  const views = fakeViewFactory();
  const extras = createV6Extras({
    client: { plots: { waveform } },
    createView: views.createView,
    createChrome: () => chrome,
  });
  return { extras, waveform, chrome, views };
}

describe("createV6Extras", () => {
  it("frames the section as one panel with a header bar and two closed disclosures", () => {
    // Given / When
    const { extras, chrome } = setup();
    const panels = [...extras.root.querySelectorAll("details")];

    // Then: рамка и классы-пины секции analysis-v2.
    expect(extras.root.classList.contains("panel")).toBe(true);
    expect(extras.root.classList.contains("analysis-v2")).toBe(true);
    expect(extras.root.classList.contains("v6-extras")).toBe(true);
    expect(extras.root.classList.contains("lnt-w1-chrome")).toBe(true);
    expect(extras.root.getAttribute("data-section")).toBe("analysis-v2");
    expect(extras.root.firstElementChild).toBe(chrome.bar);
    expect(panels).toHaveLength(2);
    expect(panels.map((panel) => panel.getAttribute("data-extra"))).toEqual(["waveform", "w1"]);
    expect(panels.every((panel) => panel.open === false)).toBe(true);
  });

  it("puts the injected chrome root inside the w1 details body", () => {
    // Given / When
    const { extras, chrome } = setup();
    const w1 = extras.root.querySelector("[data-extra=w1]");

    // Then
    expect(w1?.querySelector(".fake-w1-chrome")).toBe(chrome.root);
    expect(w1?.querySelector(".fake-w1-bar")).toBeNull();
  });

  it("publishes the chrome summary into the collapsed w1 header", () => {
    // Given / When
    const { extras } = setup();

    // Then: сводка читается без раскрытия.
    expect(extras.root.querySelector("[data-role=w1-sum-value]")?.textContent).toBe(
      "панелей 0 · скаляров 0/4",
    );
  });

  it("drives the chrome from the pair base only", () => {
    // Given
    const { extras, chrome } = setup();

    // When
    extras.setPair("sess-a", "sess-b");

    // Then
    expect(chrome.sessions).toEqual(["sess-a"]);
  });

  it("clears the chrome when the pair is empty", () => {
    // Given
    const { extras, chrome } = setup();
    extras.setPair("sess-a", null);

    // When
    extras.setPair(null, null);

    // Then
    expect(chrome.sessions).toEqual(["sess-a", null]);
  });

  it("does not load the waveform while the details stay closed", () => {
    // Given
    const { extras, waveform } = setup();

    // When
    extras.setPair("a", null);

    // Then
    expect(waveform).not.toHaveBeenCalled();
  });

  it("loads CH1 and renders when the waveform details open after setPair", async () => {
    // Given
    const { extras, waveform, views } = setup();
    extras.setPair("a", null);
    const wave = extras.root.querySelector("[data-extra=waveform]");
    expect(wave).toBeInstanceOf(HTMLDetailsElement);
    if (!(wave instanceof HTMLDetailsElement)) return;

    // When
    wave.open = true;
    wave.dispatchEvent(new Event("toggle"));

    // Then
    expect(waveform).toHaveBeenCalledWith("a", "ch1");
    await Promise.resolve();
    expect(views.renders.length).toBeGreaterThan(0);
  });

  it("tears down the chart and the injected chrome", () => {
    // Given
    const { extras, chrome } = setup();
    extras.setPair("a", null);

    // When
    extras.destroy();

    // Then
    expect(chrome.destroy).toHaveBeenCalled();
  });
});
