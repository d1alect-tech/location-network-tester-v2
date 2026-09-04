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

/** ENBW окна Ханна: RBW ≈ 1.5 × df. df — только из payload-поля resolution_hz
 * (шаг полной сетки анализа), НЕ из децимированной сетки frequency_hz. */
export const HANN_ENBW = 1.5;

const ruCompact = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

/** «RBW ≈ X Гц» из честного df; null — подписи нет ( hidden ). */
export function formatRbw(resolutionHz: unknown): string | null {
  if (typeof resolutionHz !== "number" || !Number.isFinite(resolutionHz) || resolutionHz <= 0) {
    return null;
  }
  return `RBW ≈ ${ruCompact.format(HANN_ENBW * resolutionHz)} Гц`;
}

export type InputReferenceInfo = { readonly status: string | null; readonly reason: string | null };

/** Квалификация входа из detail().analysis.ch1_input_reference (открытый объект бэкенда). */
export function inputReferenceOf(analysis: unknown): InputReferenceInfo {
  if (typeof analysis !== "object" || analysis === null) return { status: null, reason: null };
  const reference = Reflect.get(analysis, "ch1_input_reference");
  if (typeof reference !== "object" || reference === null) return { status: null, reason: null };
  const status = Reflect.get(reference, "status");
  const reason = Reflect.get(reference, "reason_code");
  return {
    status: typeof status === "string" ? status : null,
    reason: typeof reason === "string" ? reason : null,
  };
}

export function isPlane(value: string | null): value is SpectrumPlane {
  return value === "scope" || value === "input-referred";
}

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

/** Входная плоскость маппится на scope-контракт: excess-PSD тоже В²/Гц. */
function planePayload(payload: SpectrumPayload | InputReferredSpectrumPayload): SpectrumPayload {
  if ("psd_v2_per_hz" in payload) return payload;
  return {
    frequency_hz: [...payload.frequency_hz],
    psd_v2_per_hz: [...payload.input_referred_excess_psd_v2_per_hz],
    point_count: payload.point_count,
    resolution_hz: payload.resolution_hz,
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
  const planeScopeBtn = el("button", {
    className: "btn-quiet plane-btn",
    text: "Скоп",
    attrs: {
      type: "button",
      "data-spectrum-plane": "scope",
      "aria-pressed": "true",
      title: "Плоскость осциллографа",
    },
  }) as HTMLButtonElement;
  const planeReferredBtn = el("button", {
    className: "btn-quiet plane-btn",
    text: "Вход",
    attrs: {
      type: "button",
      "data-spectrum-plane": "input-referred",
      "aria-pressed": "false",
      title: "Input-referred excess-PSD на входе CH1",
    },
  }) as HTMLButtonElement;
  const planeToggle = el(
    "div",
    { className: "plane-toggle", attrs: { role: "group", "aria-label": "Плоскость спектра" } },
    [planeScopeBtn, planeReferredBtn],
  );
  const rbw = el("span", {
    className: "plane-rbw num",
    attrs: {
      "data-spectrum-rbw": "",
      hidden: "",
      title: "Полоса разрешения ≈ 1.5 × df (окно Ханна, ENBW)",
    },
  });
  const gramBar = el("div", { className: "gram-bar" });
  const header = el("div", { className: "panel-hd" }, [
    title,
    viewToggle,
    planeToggle,
    rbw,
    gramBar,
  ]);
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

  let plane: SpectrumPlane = "scope";
  let lastA: string | null = null;
  let lastB: string | null = null;
  let referredEnabled = false;

  /** Спектр в активной плоскости; вход при 404/409 откатывается на скоп. */
  async function fetchPlaneSpectrum(name: string): Promise<SpectrumPayload> {
    const plots = opts.client.plots;
    if (plane !== "input-referred" || plots.spectrumInputReferred === undefined) {
      return plots.spectrum(name);
    }
    try {
      return planePayload(await plots.spectrumInputReferred(name));
    } catch {
      return plots.spectrum(name);
    }
  }

  function paintPlane(analysis: unknown): void {
    const info = inputReferenceOf(analysis);
    referredEnabled = info.status === "available";
    planeReferredBtn.disabled = !referredEnabled;
    planeReferredBtn.title = referredEnabled
      ? "Input-referred excess-PSD на входе CH1"
      : (info.reason ?? "input-reference недоступен");
    if (!referredEnabled) plane = "scope";
    planeScopeBtn.setAttribute("aria-pressed", String(plane === "scope"));
    planeReferredBtn.setAttribute("aria-pressed", String(plane === "input-referred"));
  }

  function paintRbw(payload: SpectrumPayload | null): void {
    const text = payload === null ? null : formatRbw(payload.resolution_hz);
    if (text === null) {
      rbw.textContent = "";
      rbw.setAttribute("hidden", "");
      return;
    }
    rbw.textContent = text;
    rbw.removeAttribute("hidden");
  }

  async function load(a: string, b: string | null): Promise<void> {
    lastA = a;
    lastB = b;
    const [payloadA, payloadB, detail] = await Promise.all([
      fetchPlaneSpectrum(a),
      b === null ? Promise.resolve(null) : fetchPlaneSpectrum(b),
      opts.client.plots.detail(a),
    ]);
    paintPlane(detail.analysis);
    paintRbw(payloadA);
    peaksA = peaksFromDetail(detailForPeaks(a, detail));
    const suffix = plane === "input-referred" ? " · вход" : "";
    const styleA: SeriesStyle = { color: theme.accentA, label: `${a}${suffix}` };
    const styleB: SeriesStyle = {
      color: theme.accentB,
      label: `${b ?? ""}${suffix}`,
      dash: DASH_B,
    };
    chart.render(overlayRequest(payloadA, payloadB, styleA, styleB, peaksA));
  }

  function setPlane(next: SpectrumPlane): void {
    if (next === plane) return;
    if (next === "input-referred" && !referredEnabled) return;
    plane = next;
    planeScopeBtn.setAttribute("aria-pressed", String(next === "scope"));
    planeReferredBtn.setAttribute("aria-pressed", String(next === "input-referred"));
    if (lastA === null) return;
    void load(lastA, lastB);
  }

  planeScopeBtn.addEventListener("click", () => setPlane("scope"));
  planeReferredBtn.addEventListener("click", () => setPlane("input-referred"));

  return {
    root,
    gramHost,
    gramBar,
    load,
    setView,
    plane: () => plane,
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
