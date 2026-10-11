/** B3 Section-контракт секции спектр+грам (G5): единая шапка группами,
 * грам-контролы в своём кластере (заём слотов снят), teardown без оракулов. */

import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import type { SpectrumPayload } from "../../api/types-plots";
import type { ChartHandle } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { createSpectrumGramSection } from "./spectrumGramSection";

const SPECTRUM: SpectrumPayload = {
  frequency_hz: [100, 1000],
  psd_v2_per_hz: [1e-4, 1e-6],
  point_count: 2,
};

type TrackedView = ChartHandle & { destroyed: boolean; syncKey: string | undefined };

function makeViewFactory(): {
  createView: (options: UplotViewOptions) => ChartHandle;
  views: TrackedView[];
} {
  const views: TrackedView[] = [];
  const createView = (options: UplotViewOptions): ChartHandle => {
    const root = document.createElement("div");
    options.container.append(root);
    const handle: TrackedView = {
      root,
      destroyed: false,
      syncKey: options.syncKey,
      render() {},
      applyTheme() {},
      getData: () => null,
      destroy() {
        this.destroyed = true;
      },
    };
    views.push(handle);
    return handle;
  };
  return { createView, views };
}

function makeClient() {
  return {
    plots: {
      spectrum: async () => SPECTRUM,
      detail: async () => ({ analysis: {} }),
    },
    analysis: { artifactBytes: async () => new ArrayBuffer(0) },
    requestJson: async () => {
      throw new ApiError("http", { status: 404 });
    },
  };
}

describe("createSpectrumGramSection", () => {
  it("exposes the Section contract: root, setPair, destroy", () => {
    const { createView } = makeViewFactory();
    const section = createSpectrumGramSection({ client: makeClient(), createView });

    expect(section.root).toBeInstanceOf(HTMLElement);
    expect(section.root.getAttribute("data-section")).toBe("spectrum-gram");
    expect(typeof section.setPair).toBe("function");
    expect(typeof section.destroy).toBe("function");
    section.destroy();
  });

  it("builds one header of three labelled clusters; gram controls live in the gram cluster", () => {
    const { createView } = makeViewFactory();
    const section = createSpectrumGramSection({ client: makeClient(), createView });

    const header = section.root.querySelector(".panel-hd.signal-hd");
    expect(header).toBeInstanceOf(HTMLElement);
    const clusters = header?.querySelectorAll("[data-signal-cluster]");
    expect(clusters?.length).toBe(3);
    expect(
      header?.querySelector('[data-signal-cluster="view"] [data-spectrum-view]'),
    ).toBeInstanceOf(HTMLButtonElement);
    expect(
      header?.querySelector('[data-signal-cluster="spectrum"] [data-spectrum-plane]'),
    ).toBeInstanceOf(HTMLButtonElement);
    const gramCluster = header?.querySelector('[data-signal-cluster="gram"]');
    expect(gramCluster?.querySelector("[data-gram-bar] [data-spectrogram-mode]")).toBeInstanceOf(
      HTMLButtonElement,
    );
    expect(gramCluster?.querySelector("[data-spectrogram-detector]")).toBeInstanceOf(
      HTMLButtonElement,
    );
    // Заём слотов снят: органы грама не в теле спектральной панели.
    expect(section.root.querySelector(".panel-bd [data-spectrogram-mode]")).toBeNull();
    section.destroy();
  });

  it("marks the live cluster active: spectrum first, gram after the view toggle", () => {
    const { createView } = makeViewFactory();
    const section = createSpectrumGramSection({ client: makeClient(), createView });
    const gramCluster = section.root.querySelector('[data-signal-cluster="gram"]');
    const spectrumCluster = section.root.querySelector('[data-signal-cluster="spectrum"]');

    expect(spectrumCluster?.hasAttribute("data-active")).toBe(true);
    expect(gramCluster?.hasAttribute("data-active")).toBe(false);
    section.root.querySelector<HTMLButtonElement>('[data-spectrum-view="gram"]')?.click();
    expect(gramCluster?.hasAttribute("data-active")).toBe(true);
    expect(spectrumCluster?.hasAttribute("data-active")).toBe(false);
    section.root.querySelector<HTMLButtonElement>('[data-spectrum-view="spectrum"]')?.click();
    expect(spectrumCluster?.hasAttribute("data-active")).toBe(true);
    section.destroy();
  });

  it("setPair updates spectrum and gram together", async () => {
    const { createView, views } = makeViewFactory();
    const section = createSpectrumGramSection({ client: makeClient(), createView });

    await section.setPair("a", "b");

    expect(views[0]?.root.parentElement).toBeInstanceOf(HTMLElement);
    expect(section.payloads()).toEqual({ a: SPECTRUM, b: SPECTRUM });
    // Грам без артефактов: честная пустота, не ошибка.
    expect(section.root.querySelector("[data-gram-bar] .gram-scale")?.textContent).toContain(
      "нет спектрограммы",
    );
    section.destroy();
  });

  it("destroy releases the sync key: a remount leaves exactly one live chart per key", async () => {
    const first = makeViewFactory();
    const sectionA = createSpectrumGramSection({
      client: makeClient(),
      createView: first.createView,
    });
    await sectionA.setPair("a", null);
    sectionA.destroy();

    const second = makeViewFactory();
    const sectionB = createSpectrumGramSection({
      client: makeClient(),
      createView: second.createView,
    });
    await sectionB.setPair("a", null);

    const liveKeys = new Map<string, number>();
    for (const view of [...first.views, ...second.views]) {
      if (view.destroyed) continue;
      const key = view.syncKey ?? "";
      liveKeys.set(key, (liveKeys.get(key) ?? 0) + 1);
    }
    expect(first.views.every((view) => view.destroyed)).toBe(true);
    expect([...liveKeys.values()]).toEqual([1]);

    sectionB.destroy();
    expect(second.views.every((view) => view.destroyed)).toBe(true);
  });
});
