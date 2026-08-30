import { describe, expect, it, vi } from "vitest";
import type { WaveformPayload } from "../../api/types-plots";
import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { createV6Extras } from "./v6Extras";

const WAVE: WaveformPayload = {
  channel: "ch1",
  time_s: [0, 1],
  voltage_v: [0.1, 0.2],
  point_count: 2,
};

function fakeChrome() {
  const root = document.createElement("div");
  root.className = "fake-w1-chrome";
  return { root, destroy: vi.fn() };
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
  it("builds two closed details for waveform and w1", () => {
    // Given / When
    const { extras } = setup();
    const panels = [...extras.root.querySelectorAll("details")];

    // Then
    expect(extras.root.classList.contains("v6-extras")).toBe(true);
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
  });

  it("does not load the waveform while the details stay closed", () => {
    // Given
    const { extras, waveform } = setup();

    // When
    extras.setSession("a");

    // Then
    expect(waveform).not.toHaveBeenCalled();
  });

  it("loads CH1 and renders when the waveform details open after setSession", async () => {
    // Given
    const { extras, waveform, views } = setup();
    extras.setSession("a");
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
});
