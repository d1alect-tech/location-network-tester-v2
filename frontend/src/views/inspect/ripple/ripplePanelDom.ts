/** DOM-скелет панели «Риппл / шум»: фиксированные слоты значений и
 * управляющих элементов. Строится один раз; paint только меняет текст и
 * data-value, поэтому ширина слотов не зависит от данных. */

import { el } from "../../../components/primitives/dom";
import { RIPPLE_DASH } from "./rippleModel";
import type { RippleMetricKey } from "./rippleModel";

const METRICS: ReadonlyArray<{ key: RippleMetricKey; label: string; note: string }> = [
  { key: "mean", label: "Среднее", note: "по записи" },
  { key: "rms-ac", label: "RMS AC", note: "полная запись" },
  { key: "vpp", label: "Размах Vpp", note: "полный размах" },
  { key: "band", label: "Полоса", note: "программная полоса" },
];

export type RippleCardDom = {
  readonly root: HTMLElement;
  readonly value: HTMLElement;
  readonly note: HTMLElement;
};

export type RipplePanelDom = {
  readonly root: HTMLElement;
  readonly chartHost: HTMLElement;
  readonly message: HTMLElement;
  readonly bandSelect: HTMLSelectElement;
  readonly psd: HTMLButtonElement;
  readonly asd: HTMLButtonElement;
  readonly sessionEl: HTMLElement;
  readonly chips: HTMLElement[];
  readonly cards: Map<RippleMetricKey, RippleCardDom>;
  readonly intervalSlots: HTMLElement[];
  readonly intervalCount: HTMLElement;
  readonly qc: HTMLElement;
  readonly spectrumMeta: HTMLElement;
  readonly baselineStatus: HTMLElement;
  readonly baselineRms: HTMLElement;
  readonly baselineVpp: HTMLElement;
  readonly baselineSession: HTMLElement;
  readonly chartEmpty: HTMLElement;
};

function chip(name: string): HTMLElement {
  return el("span", { className: "ripple-chip", attrs: { "data-chip": name, title: "" } });
}

function card(key: RippleMetricKey, label: string, noteText: string): RippleCardDom {
  const value = el("span", { className: "ripple-card-value", text: RIPPLE_DASH });
  const note = el("span", { className: "ripple-card-note", text: noteText });
  const root = el(
    "div",
    {
      className: "ripple-card",
      attrs: { "data-metric": key, "data-ripple-slot": "", "data-value": "null", title: "" },
    },
    [el("span", { className: "ripple-card-label", text: label }), value, note],
  );
  return { root, value, note };
}

export function createRipplePanelDom(): RipplePanelDom {
  const cards = new Map<RippleMetricKey, RippleCardDom>();
  const metricGrid = el("div", {
    className: "ripple-metrics",
    attrs: { "data-ripple-metrics": "" },
  });
  for (const spec of METRICS) {
    const built = card(spec.key, spec.label, spec.note);
    cards.set(spec.key, built);
    metricGrid.append(built.root);
  }

  const intervalSlots: HTMLElement[] = [];
  for (let index = 0; index < 3; index += 1) {
    intervalSlots.push(
      el("span", {
        className: "ripple-interval",
        text: "—",
        attrs: {
          "data-interval-slot": String(index),
          "data-ripple-slot": "",
          "data-value": "null",
        },
      }),
    );
  }
  const intervalCount = el("span", {
    className: "ripple-intervals-count",
    attrs: { "data-interval-count": "" },
  });
  const intervals = el("div", { className: "ripple-intervals" }, [
    el("span", { className: "ripple-intervals-label", text: "Vpp по окнам" }),
    ...intervalSlots,
    intervalCount,
  ]);
  const qc = el("span", { className: "ripple-qc", attrs: { "data-ripple-qc": "", title: "" } });
  const main = el("div", { className: "ripple-main" }, [metricGrid, intervals, qc]);

  const spectrumMeta = el("span", {
    className: "ripple-chart-meta",
    attrs: { "data-role": "spectrum-meta", title: "" },
  });
  const bandSelect = el("select", {
    className: "ctl ripple-band",
    attrs: { "data-ripple-band": "", "aria-label": "Сохранённая полоса" },
  }) as HTMLSelectElement;
  bandSelect.hidden = true;
  const psd = el("button", {
    className: "ripple-mode-btn",
    text: "PSD",
    attrs: { type: "button", "data-ripple-mode": "psd", "aria-pressed": "true" },
  }) as HTMLButtonElement;
  const asd = el("button", {
    className: "ripple-mode-btn",
    text: "ASD",
    attrs: { type: "button", "data-ripple-mode": "asd", "aria-pressed": "false" },
  }) as HTMLButtonElement;
  const toggle = el(
    "div",
    { className: "ripple-toggle", attrs: { role: "group", "aria-label": "Представление спектра" } },
    [psd, asd],
  );
  const chartHeader = el("figcaption", { className: "ripple-chart-hd" }, [
    el("span", { className: "ripple-chart-title", text: "Спектр (сохранённый)" }),
    spectrumMeta,
    bandSelect,
    toggle,
  ]);
  const chartHost = el("div", {
    className: "ripple-chart-host",
    attrs: { "data-role": "chart-host" },
  });
  const chartEmpty = el("p", {
    className: "ripple-chart-empty",
    text: "сессия не выбрана",
    attrs: { "data-role": "chart-empty" },
  });
  chartHost.hidden = true;
  const chart = el("figure", { className: "ripple-chart" }, [chartHeader, chartHost, chartEmpty]);

  const baselineStatus = el("span", {
    className: "ripple-baseline-status",
    attrs: { "data-baseline-status": "" },
  });
  const baselineRms = el("span", {
    className: "ripple-baseline-value",
    attrs: { "data-baseline-rms": "", "data-value": "null" },
  });
  const baselineVpp = el("span", {
    className: "ripple-baseline-value",
    attrs: { "data-baseline-vpp": "", "data-value": "null" },
  });
  const baselineSession = el("span", {
    className: "ripple-baseline-session",
    attrs: { "data-baseline-session": "" },
  });
  const baseline = el(
    "div",
    { className: "ripple-baseline", attrs: { "data-ripple-baseline": "", title: "" } },
    [
      el("span", { className: "ripple-baseline-label", text: "Фон рядом" }),
      baselineStatus,
      el("span", { className: "ripple-baseline-cap", text: "RMS AC" }),
      baselineRms,
      el("span", { className: "ripple-baseline-cap", text: "Vpp" }),
      baselineVpp,
      baselineSession,
    ],
  );

  const message = el("p", {
    className: "ripple-message",
    attrs: { "data-role": "ripple-message", role: "status", "aria-live": "polite" },
  });
  const sessionEl = el("span", {
    className: "ripple-session",
    attrs: { "data-ripple-session": "" },
  });
  const chips = [chip("volts"), chip("band"), chip("settling"), chip("sample")];
  const titleBlock = el("div", { className: "ripple-titleblock" }, [
    el("h2", { className: "panel-title", text: "Риппл / шум" }),
    sessionEl,
  ]);
  const header = el("div", { className: "panel-hd ripple-hd" }, [
    titleBlock,
    el("div", { className: "ripple-chips" }, chips),
  ]);
  const body = el("div", { className: "panel-bd ripple-bd" }, [main, chart, baseline, message]);
  const root = el(
    "section",
    {
      className: "panel ripple-panel",
      attrs: {
        "data-ripple-panel": "",
        "data-state": "idle",
        "data-session-id": "",
        "data-availability": "none",
        "data-error": "",
        "data-reason": "",
        "aria-label": "Риппл и шум",
      },
    },
    [header, body],
  );

  return {
    root,
    chartHost,
    message,
    bandSelect,
    psd,
    asd,
    sessionEl,
    chips,
    cards,
    intervalSlots,
    intervalCount,
    qc,
    spectrumMeta,
    baselineStatus,
    baselineRms,
    baselineVpp,
    baselineSession,
    chartEmpty,
  };
}
