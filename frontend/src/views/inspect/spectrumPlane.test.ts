/** Плоскость спектра scope/input-referred: хелперы, тумблер, RBW, disable-правило.
 * RED: RBW из payload-поля resolution_hz; disable по detail().analysis.ch1_input_reference.status. */

import { describe, expect, it, vi } from "vitest";
import type { InputReferredSpectrumPayload, SpectrumPayload } from "../../api/types-plots";
import type { ChartHandle, ChartRenderRequest } from "../../components/charts/types";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { createSpectrumPanel } from "./spectrumPanelV6";
import { formatRbw, inputReferenceOf } from "./spectrumPlaneControl";

const SCOPE_A: SpectrumPayload = {
  frequency_hz: [100, 1000, 10_000],
  psd_v2_per_hz: [1e-4, 1e-2, 1e-6],
  point_count: 3,
  resolution_hz: 100,
};

const REFERRED_A = {
  frequency_hz: [100, 1000, 10_000],
  input_referred_excess_psd_v2_per_hz: [1e-10, 1e-8, 1e-12],
  point_count: 3,
  status: "available",
  reason_code: null,
  qualified_bin_count: 3,
  total_bin_count: 3,
  resolution_hz: 100,
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

function makeClient(status: string | null, referred?: InputReferredSpectrumPayload) {
  return {
    plots: {
      spectrum: async (): Promise<SpectrumPayload> => SCOPE_A,
      spectrumInputReferred: async () => referred ?? REFERRED_A,
      detail: async () => ({
        analysis: status === null ? {} : { ch1_input_reference: { status } },
      }),
    },
  };
}

function planeButton(panel: { root: HTMLElement }, plane: string): HTMLButtonElement | null {
  return panel.root.querySelector<HTMLButtonElement>(`[data-spectrum-plane="${plane}"]`);
}

describe("formatRbw", () => {
  it("считает RBW ≈ 1.5×df (окно Ханна, ENBW) из payload-поля", () => {
    expect(formatRbw(100)).toBe("RBW ≈ 150 Гц");
  });

  it("возвращает null без честного df", () => {
    expect(formatRbw(null)).toBeNull();
    expect(formatRbw(undefined)).toBeNull();
    expect(formatRbw(Number.NaN)).toBeNull();
    expect(formatRbw(-5)).toBeNull();
    expect(formatRbw("100")).toBeNull();
  });
});

describe("inputReferenceOf", () => {
  it("читает status/reason из detail().analysis", () => {
    expect(inputReferenceOf({ ch1_input_reference: { status: "available" } })).toEqual({
      status: "available",
      reason: null,
    });
    expect(
      inputReferenceOf({
        ch1_input_reference: { status: "unavailable", reason_code: "manifest_schema_v1" },
      }),
    ).toEqual({ status: "unavailable", reason: "manifest_schema_v1" });
  });

  it("пусто при отсутствии квалификации", () => {
    expect(inputReferenceOf(null)).toEqual({ status: null, reason: null });
    expect(inputReferenceOf({})).toEqual({ status: null, reason: null });
  });
});

describe("createSpectrumPanel: тумблер плоскости", () => {
  it("по умолчанию scope нажат, RBW видна после load", async () => {
    const { createView } = makeFakeViewFactory();
    const panel = createSpectrumPanel({ client: makeClient("available"), createView });

    expect(panel.plane()).toBe("scope");
    expect(planeButton(panel, "scope")?.getAttribute("aria-pressed")).toBe("true");

    await panel.load("a", null);

    expect(panel.root.querySelector("[data-spectrum-rbw]")?.textContent).toContain("RBW ≈ 150 Гц");
  });

  it("unavailable в detail отключает кнопку входа", async () => {
    const { createView } = makeFakeViewFactory();
    const panel = createSpectrumPanel({ client: makeClient("unavailable"), createView });

    await panel.load("a", null);

    const referred = planeButton(panel, "input-referred");
    expect(referred?.disabled).toBe(true);
    expect(panel.plane()).toBe("scope");
  });

  it("available включает вход и клик переключает источник трасс", async () => {
    const { createView, views } = makeFakeViewFactory();
    const spectrumInputReferred = vi.fn(async () => REFERRED_A);
    const client = {
      plots: {
        spectrum: async (): Promise<SpectrumPayload> => SCOPE_A,
        spectrumInputReferred,
        detail: async () => ({ analysis: { ch1_input_reference: { status: "available" } } }),
      },
    };
    const panel = createSpectrumPanel({ client, createView });
    await panel.load("a", null);
    expect(planeButton(panel, "input-referred")?.disabled).toBe(false);

    planeButton(panel, "input-referred")?.click();
    await vi.waitFor(() => {
      expect(spectrumInputReferred).toHaveBeenCalledWith("a");
    });
    expect(panel.plane()).toBe("input-referred");
    await vi.waitFor(() => {
      expect((views[0]?.renders.length ?? 0) >= 2).toBe(true);
    });
    const last = views[0]?.renders[views[0]?.renders.length - 1];
    expect(last?.series[0]?.values).toEqual([1e-10, 1e-8, 1e-12]);

    planeButton(panel, "scope")?.click();
    expect(panel.plane()).toBe("scope");
    expect(planeButton(panel, "scope")?.getAttribute("aria-pressed")).toBe("true");
  });

  it("404 входа откатывается на scope без падения", async () => {
    const { createView, views } = makeFakeViewFactory();
    const client = {
      plots: {
        spectrum: async (): Promise<SpectrumPayload> => SCOPE_A,
        spectrumInputReferred: async (): Promise<never> => {
          throw new Error("404");
        },
        detail: async () => ({ analysis: { ch1_input_reference: { status: "available" } } }),
      },
    };
    const panel = createSpectrumPanel({ client, createView });
    await panel.load("a", null);

    planeButton(panel, "input-referred")?.click();
    await vi.waitFor(() => {
      expect((views[0]?.renders.length ?? 0) >= 2).toBe(true);
    });
    const last = views[0]?.renders[views[0]?.renders.length - 1];
    expect(last?.series[0]?.values).toEqual([1e-4, 1e-2, 1e-6]);
  });
});
