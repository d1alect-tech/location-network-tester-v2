/** Единое сигнальное окно инспекции v6: uPlot-спектр A/B и слот спектрограммы. */

import type {
  InputReferredSpectrumPayload,
  SessionDetailPayload,
  SpectrumPayload,
  SpectrumPlane,
} from "../../api/types-plots";
import { createPeaksPlugin } from "../../components/charts/annotations";
import { readChartTheme } from "../../components/charts/theme";
import type { ChartHandle, ChartPeak, ChartRenderRequest } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import type { UplotViewOptions } from "../../components/charts/uplotView";
import { peaksFromDetail, spectrumToRequest } from "../../components/charts/viewModels";
import type { SeriesStyle } from "../../components/charts/viewModels";
import { el } from "../../components/primitives/dom";
import { createPlaneControl, planePayload } from "./spectrumPlaneControl";

export type SpectrumView = "spectrum" | "gram";

export type SpectrumPanelClient = {
  readonly plots: {
    spectrum: (
      name: string,
      maxPoints?: number,
      o?: { readonly signal?: AbortSignal },
    ) => Promise<SpectrumPayload>;
    spectrumInputReferred?: (
      name: string,
      maxPoints?: number,
      o?: { readonly signal?: AbortSignal },
    ) => Promise<InputReferredSpectrumPayload>;
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
  plane(): SpectrumPlane;
  setPlane(plane: SpectrumPlane): void;
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
  let reloadPlane: () => void = () => undefined;
  const planeControl = createPlaneControl(() => reloadPlane());
  const gramBar = el("div", { className: "gram-bar" });
  const header = el("div", { className: "panel-hd" }, [
    title,
    viewToggle,
    planeControl.toggle,
    planeControl.rbw,
    gramBar,
  ]);
  const frame = el("div", { className: "frame" });
  const gramHost = el("div", { className: "gram" });
  const statusText = el("span", {});
  const retryButton = el("button", {
    className: "lnt-btn btn-quiet",
    text: "Пересчитать спектр",
    attrs: { type: "button" },
  }) as HTMLButtonElement;
  retryButton.addEventListener("click", () => reloadPlane());
  const status = el(
    "div",
    { className: "spectrum-status", attrs: { role: "status", "data-spectrum-status": "" } },
    [statusText, retryButton],
  );
  status.hidden = true;
  const body = el("div", { className: "panel-bd" }, [status, frame, gramHost]);
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

  let lastA: string | null = null;
  let lastB: string | null = null;
  let rendered = false;

  /** Спектр в активной плоскости; вход при 404/409 откатывается на скоп. */
  async function fetchPlaneSpectrum(name: string): Promise<SpectrumPayload> {
    const plots = opts.client.plots;
    if (planeControl.plane() !== "input-referred" || plots.spectrumInputReferred === undefined) {
      return plots.spectrum(name);
    }
    try {
      return planePayload(await plots.spectrumInputReferred(name));
    } catch {
      return plots.spectrum(name);
    }
  }

  async function load(a: string, b: string | null): Promise<void> {
    lastA = a;
    lastB = b;
    status.hidden = false;
    retryButton.hidden = true;
    statusText.textContent = "Загрузка спектра…";
    root.classList.add("is-loading");
    root.classList.remove("is-stale");
    try {
      const [payloadA, payloadB, detail] = await Promise.all([
        fetchPlaneSpectrum(a),
        b === null ? Promise.resolve(null) : fetchPlaneSpectrum(b),
        opts.client.plots.detail(a),
      ]);
      planeControl.paintPlane(detail.analysis);
      planeControl.paintRbw(payloadA);
      peaksA = peaksFromDetail(detailForPeaks(a, detail));
      const suffix = planeControl.plane() === "input-referred" ? " · вход" : "";
      const styleA: SeriesStyle = { color: theme.accentA, label: `${a}${suffix}` };
      const styleB: SeriesStyle = {
        color: theme.accentB,
        label: `${b ?? ""}${suffix}`,
        dash: DASH_B,
      };
      chart.render(overlayRequest(payloadA, payloadB, styleA, styleB, peaksA));
      rendered = true;
      status.hidden = true;
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      retryButton.hidden = false;
      statusText.textContent = rendered
        ? `Данные устарели: ${reason}. Показан последний спектр.`
        : `Не удалось загрузить спектр: ${reason}.`;
      if (rendered) root.classList.add("is-stale");
    } finally {
      root.classList.remove("is-loading");
    }
  }

  reloadPlane = () => {
    if (lastA === null) return;
    void load(lastA, lastB);
  };

  function setPlane(next: SpectrumPlane): void {
    if (planeControl.requestPlane(next)) reloadPlane();
  }

  return {
    root,
    gramHost,
    gramBar,
    load,
    setView,
    plane: () => planeControl.plane(),
    setPlane,
    view: () => current,
    onViewChange(cb) {
      viewChange = cb;
    },
    destroy() {
      chart.destroy();
    },
  };
}
