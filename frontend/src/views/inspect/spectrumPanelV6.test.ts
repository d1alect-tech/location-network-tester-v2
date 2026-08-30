import { describe, expect, it, vi } from "vitest";
import type { SpectrumPayload } from "../../api/types-plots";
import type { ChartHandle, ChartRenderRequest } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { createSpectrumPanel } from "./spectrumPanelV6";

const SPECTRUM_A: SpectrumPayload = {
  frequency_hz: [100, 1000, 10_000],
  psd_v2_per_hz: [1e-4, 1e-2, 1e-6],
  point_count: 3,
};

const SPECTRUM_B: SpectrumPayload = {
  frequency_hz: [100, 1000, 10_000],
  psd_v2_per_hz: [2e-4, 2e-2, 2e-6],
  point_count: 3,
};

interface FakeView extends ChartHandle {
  renders: ChartRenderRequest[];
}

function makeFakeViewFactory(): {
  createView: (options: UplotViewOptions) => ChartHandle;
  views: FakeView[];
} {
  const views: FakeView[] = [];
  const createView = (options: UplotViewOptions): ChartHandle => {
    const root = document.createElement("div");
    options.container.append(root);
    const handle: FakeView = {
      root,
      renders: [],
      render(request) {
        this.renders.push(request);
      },
      applyTheme() {},
      getData: () => null,
      destroy() {},
    };
    views.push(handle);
    return handle;
  };
  return { createView, views };
}

function makeClient() {
  return {
    plots: {
      spectrum: async (name: string): Promise<SpectrumPayload> =>
        name === "a" ? SPECTRUM_A : SPECTRUM_B,
      detail: async () => ({ analysis: {} }),
    },
  };
}

describe("createSpectrumPanel", () => {
  it("defaults to spectrum view without is-gram and exposes both toggle buttons", () => {
    const { createView } = makeFakeViewFactory();
    const panel = createSpectrumPanel({ client: makeClient(), createView });

    expect(panel.view()).toBe("spectrum");
    expect(panel.root.classList.contains("is-gram")).toBe(false);
    expect(panel.root.querySelector('[data-spectrum-view="spectrum"]')).toBeInstanceOf(
      HTMLButtonElement,
    );
    expect(panel.root.querySelector('[data-spectrum-view="gram"]')).toBeInstanceOf(
      HTMLButtonElement,
    );
  });

  it("toggles is-gram and aria-pressed and notifies onViewChange", () => {
    const { createView } = makeFakeViewFactory();
    const panel = createSpectrumPanel({ client: makeClient(), createView });
    const onViewChange = vi.fn();
    panel.onViewChange(onViewChange);

    panel.root.querySelector<HTMLButtonElement>('[data-spectrum-view="gram"]')?.click();

    expect(panel.root.classList.contains("is-gram")).toBe(true);
    expect(
      panel.root.querySelector('[data-spectrum-view="gram"]')?.getAttribute("aria-pressed"),
    ).toBe("true");
    expect(onViewChange).toHaveBeenCalledWith("gram");

    panel.root.querySelector<HTMLButtonElement>('[data-spectrum-view="spectrum"]')?.click();

    expect(panel.root.classList.contains("is-gram")).toBe(false);
    expect(
      panel.root.querySelector('[data-spectrum-view="spectrum"]')?.getAttribute("aria-pressed"),
    ).toBe("true");
    expect(onViewChange).toHaveBeenCalledWith("spectrum");
  });

  it("load(a, b) renders one overlay request with solid A and dashed B", async () => {
    const { createView, views } = makeFakeViewFactory();
    const panel = createSpectrumPanel({ client: makeClient(), createView });

    await panel.load("a", "b");

    const request = views[0]?.renders[0];
    expect(request?.series).toHaveLength(2);
    expect(request?.series[0]?.dash).toBeUndefined();
    expect(request?.series[1]?.dash).toEqual([6, 4]);
    expect(request?.xLabel).toBe("");
    expect(request?.xLog).toBe(true);
  });
});
