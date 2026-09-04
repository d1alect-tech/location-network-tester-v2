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

  it("load(a, null) appends max-hold trace when payload carries it", async () => {
    const payload: SpectrumPayload = {
      ...SPECTRUM_A,
      psd_max_hold_v2_per_hz: [2e-4, 3e-2, 2e-6],
    };
    const { createView, views } = makeFakeViewFactory();
    const panel = createSpectrumPanel({
      client: {
        plots: {
          spectrum: async () => payload,
          detail: async () => ({ analysis: {} }),
        },
      },
      createView,
    });

    await panel.load("a", null);

    const request = views[0]?.renders[0];
    expect(request?.series).toHaveLength(2);
    expect(request?.series[1]?.label).toContain("max-hold");
    expect(request?.series[1]?.values).toEqual([2e-4, 3e-2, 2e-6]);
  });

  it("load(a, null) renders a single series without max-hold key", async () => {
    const { createView, views } = makeFakeViewFactory();
    const panel = createSpectrumPanel({ client: makeClient(), createView });

    await panel.load("a", null);

    expect(views[0]?.renders[0]?.series).toHaveLength(1);
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

const QUEUE_A_PAYLOAD: SpectrumPayload = {
  frequency_hz: [10, 20, 40],
  psd_v2_per_hz: [1e-12, 2e-12, 1.5e-12],
  point_count: 3,
};

function mountQueueA(
  spectrumImpl: () => Promise<SpectrumPayload>,
  render: () => void = () => undefined,
) {
  const spectrum = vi.fn(spectrumImpl);
  const detail = vi.fn(async (_name: string) => ({ analysis: {} }));
  const { createView } = makeFakeViewFactory();
  const panel = createSpectrumPanel({
    client: { plots: { spectrum, detail } },
    createView: (options) => {
      const view = createView(options);
      const origin = view.render.bind(view);
      view.render = (request) => {
        render();
        origin(request);
      };
      return view;
    },
  });
  document.body.replaceChildren(panel.root);
  return { panel, spectrum };
}

function spectrumStatus(): HTMLElement | null {
  return document.querySelector<HTMLElement>("[data-spectrum-status]");
}

describe("spectrumPanelV6: скелетон, stale-метка и CTA пересчёта (очередь A1)", () => {
  it("во время загрузки показывает русскую строку состояния", async () => {
    // Given
    let release!: (value: SpectrumPayload) => void;
    const gate = new Promise<SpectrumPayload>((resolve) => {
      release = resolve;
    });
    const { panel } = mountQueueA(() => gate);

    // When
    const pending = panel.load("a", null);
    expect(spectrumStatus()?.hidden).toBe(false);
    expect(spectrumStatus()?.textContent).toContain("Загрузка спектра");

    // Then
    release(QUEUE_A_PAYLOAD);
    await pending;
    expect(spectrumStatus()?.hidden).toBe(true);
  });

  it("ошибка без прошлого рендера: сообщение и кнопка «Пересчитать»", async () => {
    // Given
    const { panel, spectrum } = mountQueueA(async () => {
      throw new Error("обрыв связи");
    });

    // When
    await panel.load("a", null);

    // Then
    expect(spectrumStatus()?.hidden).toBe(false);
    expect(spectrumStatus()?.textContent).toContain("Не удалось загрузить спектр");
    const retry = spectrumStatus()?.querySelector("button");
    expect(retry?.textContent).toContain("Пересчитать");
    retry?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(spectrum).toHaveBeenCalledTimes(2);
  });

  it("ошибка после успеха: график сохранён, панель помечена stale", async () => {
    // Given
    let fail = false;
    const render = vi.fn();
    const { panel } = mountQueueA(async () => {
      if (fail) throw new Error("обрыв связи");
      return QUEUE_A_PAYLOAD;
    }, render);
    await panel.load("a", null);
    expect(render).toHaveBeenCalledTimes(1);

    // When
    fail = true;
    await panel.load("a", null);

    // Then
    expect(render).toHaveBeenCalledTimes(1);
    expect(panel.root.classList.contains("is-stale")).toBe(true);
    expect(spectrumStatus()?.textContent).toContain("устарели");
  });
});
