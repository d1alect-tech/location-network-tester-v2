/** Единое сигнальное окно инспекции v6: uPlot-спектр A/B и слот спектрограммы. */

import type { SessionDetailPayload, SpectrumPayload } from "../../api/types-plots";
import { createPeaksPlugin } from "../../components/charts/annotations";
import { readChartTheme } from "../../components/charts/theme";
import type { ChartHandle, ChartPeak, ChartRenderRequest } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { peaksFromDetail, spectrumToRequest } from "../../components/charts/viewModels";
import type { SeriesStyle } from "../../components/charts/viewModels";
import { el } from "../../components/primitives/dom";

export type SpectrumView = "spectrum" | "gram";

export type SpectrumPanelClient = {
  readonly plots: {
    spectrum: (
      name: string,
      q?: unknown,
      o?: { readonly signal?: AbortSignal },
    ) => Promise<SpectrumPayload>;
    detail: (
      name: string,
      o?: { readonly signal?: AbortSignal },
    ) => Promise<{ readonly analysis?: unknown }>;
  };
};

export type SpectrumPanelOptions = {
  readonly client: SpectrumPanelClient;
  readonly createView?: (options: UplotViewOptions) => ChartHandle;
};

export type SpectrumPanelHandle = {
  readonly root: HTMLElement;
  readonly gramHost: HTMLElement;
  readonly gramBar: HTMLElement;
  load(a: string, b: string | null): Promise<void>;
  setView(view: SpectrumView): void;
  view(): SpectrumView;
  onViewChange(cb: (view: SpectrumView) => void): void;
  destroy(): void;
};

const DASH_B: readonly [number, number] = [6, 4];
const SYNC_KEY = "lnt-inspect-spectrum-v6";
const UNITS = { kind: "psd" } as const;

function assertNever(value: never): never {
  throw new Error(`unhandled spectrum view ${String(value)}`);
}

function recordFromUnknown(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null) return null;
  const record: Record<string, unknown> = {};
  for (const key of Object.keys(value)) {
    record[key] = Reflect.get(value, key);
  }
  return record;
}

function detailForPeaks(name: string, raw: { readonly analysis?: unknown }): SessionDetailPayload {
  return {
    name,
    manifest: {},
    analysis: recordFromUnknown(raw.analysis),
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}

function overlayRequest(
  payloadA: SpectrumPayload,
  payloadB: SpectrumPayload | null,
  styleA: SeriesStyle,
  styleB: SeriesStyle,
  peaks: readonly ChartPeak[],
): ChartRenderRequest {
  const requestA = spectrumToRequest(payloadA, styleA, UNITS, true, peaks);
  const series = [...requestA.series];
  if (payloadB !== null) {
    const requestB = spectrumToRequest(payloadB, styleB, UNITS, true, []);
    series.push(...requestB.series);
  }
  return { ...requestA, xLabel: "", xLog: true, series };
}

export function createSpectrumPanel(opts: SpectrumPanelOptions): SpectrumPanelHandle {
  const theme = readChartTheme();
  const viewFactory = opts.createView ?? createUplotView;
  let current: SpectrumView = "spectrum";
  let peaksA: ChartPeak[] = [];
  let viewChange: ((view: SpectrumView) => void) | undefined;

  const title = el("h2", { className: "panel-title", text: "Спектр мощности · Гц" });
  const spectrumBtn = el("button", {
    className: "btn-quiet view-toggle-btn",
    text: "Спектр",
    attrs: { type: "button", "data-spectrum-view": "spectrum", "aria-pressed": "true" },
  });
  const gramBtn = el("button", {
    className: "btn-quiet view-toggle-btn",
    text: "Спектрограмма",
    attrs: { type: "button", "data-spectrum-view": "gram", "aria-pressed": "false" },
  });
  const viewToggle = el(
    "div",
    { className: "view-toggle", attrs: { role: "group", "aria-label": "Вид сигнального окна" } },
    [spectrumBtn, gramBtn],
  );
  const gramBar = el("div", { className: "gram-bar" });
  const header = el("div", { className: "panel-hd" }, [title, viewToggle, gramBar]);
  const frame = el("div", { className: "frame" });
  const gramHost = el("div", { className: "gram" });
  const body = el("div", { className: "panel-bd" }, [frame, gramHost]);
  const root = el("section", { className: "panel", attrs: { "data-showcase": "spectrum" } }, [
    header,
    body,
  ]);

  const chart = viewFactory({
    container: frame,
    syncKey: SYNC_KEY,
    peaksPlugin: createPeaksPlugin({ peaks: () => peaksA, color: theme.accentA }),
  });

  function setView(next: SpectrumView): void {
    switch (next) {
      case "gram":
        root.classList.add("is-gram");
        break;
      case "spectrum":
        root.classList.remove("is-gram");
        break;
      default:
        assertNever(next);
    }
    current = next;
    spectrumBtn.setAttribute("aria-pressed", String(next === "spectrum"));
    gramBtn.setAttribute("aria-pressed", String(next === "gram"));
    viewChange?.(next);
  }

  spectrumBtn.addEventListener("click", () => setView("spectrum"));
  gramBtn.addEventListener("click", () => setView("gram"));

  async function load(a: string, b: string | null): Promise<void> {
    const [payloadA, payloadB, detail] = await Promise.all([
      opts.client.plots.spectrum(a),
      b === null ? Promise.resolve(null) : opts.client.plots.spectrum(b),
      opts.client.plots.detail(a),
    ]);
    peaksA = peaksFromDetail(detailForPeaks(a, detail));
    const styleA: SeriesStyle = { color: theme.accentA, label: a };
    const styleB: SeriesStyle = { color: theme.accentB, label: b ?? "", dash: DASH_B };
    chart.render(overlayRequest(payloadA, payloadB, styleA, styleB, peaksA));
  }

  return {
    root,
    gramHost,
    gramBar,
    load,
    setView,
    view: () => current,
    onViewChange(cb) {
      viewChange = cb;
    },
    destroy() {
      chart.destroy();
    },
  };
}
