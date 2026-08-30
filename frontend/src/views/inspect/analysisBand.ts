import type { SessionDetailPayload } from "../../api/types-plots";
import { el } from "../../components/primitives/dom";
import { isRecord, needleOf } from "./w1Parse";

export type Meter = {
  readonly label: string;
  readonly value: string;
  readonly unit?: string;
};

export type PeakRow = {
  readonly frequencyHz: number;
  readonly baseDb: number;
  readonly deltaDb: number | null;
  readonly prominenceDb: number;
  readonly q: number;
};

const UNAVAILABLE = "н/д";
const FLAT_DB = 0.05;
const WIDE_CHARS = 11;
const ruNumber = new Intl.NumberFormat("ru-RU");

function asFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatFixed(value: unknown, digits: number): string {
  const n = asFinite(value);
  return n === null ? UNAVAILABLE : n.toFixed(digits);
}

function formatCycles(value: unknown): string {
  const n = asFinite(value);
  return n === null ? UNAVAILABLE : String(n);
}

function formatBand(spectrum: Record<string, unknown> | null): string {
  if (spectrum === null) return UNAVAILABLE;
  const low = asFinite(spectrum.band_low_hz);
  const high = asFinite(spectrum.band_high_hz);
  if (low === null || high === null) return UNAVAILABLE;
  return `${ruNumber.format(low)}–${ruNumber.format(high)}`;
}

function formatResolution(spectrum: Record<string, unknown> | null): string {
  if (spectrum === null) return UNAVAILABLE;
  const n = asFinite(spectrum.resolution_hz);
  return n === null ? UNAVAILABLE : String(n);
}

function meter(label: string, value: string, unit?: string): Meter {
  return unit === undefined ? { label, value } : { label, value, unit };
}

export function metersFromDetail(detail: SessionDetailPayload): Meter[] {
  const analysis = detail.analysis;
  const needle = isRecord(analysis) && isRecord(analysis.needle) ? analysis.needle : null;
  const spectrum = isRecord(analysis) && isRecord(analysis.spectrum) ? analysis.spectrum : null;
  const { sigma } = needleOf(analysis);
  return [
    meter("Частота сети", formatFixed(needle?.line_frequency_hz, 7), "Гц"),
    meter("μ иглы", formatFixed(needle?.needle_mean_v, 4), "В"),
    meter("σ/μ", formatFixed(sigma, 3)),
    meter("P_async/P_sync", formatFixed(needle?.async_sync_ratio, 2)),
    meter("Циклов", formatCycles(needle === null ? null : needle.cycles_analyzed)),
    meter("Полоса", formatBand(spectrum), "Гц"),
    meter("Разрешение", formatResolution(spectrum), "Гц"),
  ];
}

function readoutCell(item: Meter): HTMLElement {
  const valueEl = el("span", { className: "readout-value" });
  valueEl.append(item.value);
  if (item.unit !== undefined) {
    valueEl.append(el("span", { className: "t-unit", text: item.unit }));
  }
  const wide = item.value.length > WIDE_CHARS ? " is-wide" : "";
  return el("div", { className: `readout-cell${wide}` }, [
    el("span", { className: "readout-label", text: item.label }),
    valueEl,
  ]);
}

function deltaCell(deltaDb: number | null): HTMLTableCellElement {
  if (deltaDb === null) {
    return el("td", { className: "num delta is-flat", text: "—" });
  }
  const flat = Math.abs(deltaDb) <= FLAT_DB;
  const glyph = flat ? "—" : deltaDb < 0 ? "▼" : "▲";
  const tone = flat ? "is-flat" : deltaDb < 0 ? "is-down" : "is-up";
  return el(
    "td",
    { className: `num delta ${tone}`, attrs: { "data-delta": deltaDb.toFixed(2) } },
    [
      el("span", {
        className: "delta-glyph",
        text: glyph,
        attrs: { "aria-hidden": "true" },
      }),
      document.createTextNode(Math.abs(deltaDb).toFixed(1)),
    ],
  );
}

function peakRow(row: PeakRow, index: number): HTMLTableRowElement {
  return el("tr", { attrs: { "data-peak-row": String(index) } }, [
    el("td", { className: "num", text: ruNumber.format(Math.round(row.frequencyHz)) }),
    el("td", { className: "num", text: row.baseDb.toFixed(2) }),
    deltaCell(row.deltaDb),
    el("td", { className: "num", text: row.prominenceDb.toFixed(2) }),
    el("td", { className: "num", text: row.q.toFixed(2) }),
  ]);
}

function heading(text: string): HTMLElement {
  return el("div", { className: "panel-hd" }, [
    el("h2", { className: "panel-title", text }),
  ]);
}

export function createAnalysisBand(): {
  readonly root: HTMLElement;
  update(input: { meters: Meter[]; peaks: PeakRow[] }): void;
} {
  const grid = el("div", { className: "readout-grid" });
  const body = el("tbody");
  const readout = el("section", { className: "panel readout" }, [
    heading("Показания базы"),
    el("div", { className: "panel-bd" }, [grid]),
  ]);
  const peaksPanel = el("section", { className: "panel" }, [
    heading("Пики спектра · дельта к базе"),
    el("div", { className: "panel-bd" }, [
      el("table", { className: "tbl tbl-compare" }, [
        el("thead", {}, [
          el("tr", {}, [
            el("th", { text: "f0, Гц", attrs: { scope: "col" } }),
            el("th", { text: "База, дБ", attrs: { scope: "col" } }),
            el("th", { text: "Δ Б−А, дБ", attrs: { scope: "col" } }),
            el("th", { text: "Выдел., дБ", attrs: { scope: "col" } }),
            el("th", { text: "Q", attrs: { scope: "col" } }),
          ]),
        ]),
        body,
      ]),
    ]),
  ]);
  const root = el("div", { className: "analysis-band" }, [readout, peaksPanel]);

  function update(input: { meters: Meter[]; peaks: PeakRow[] }): void {
    const ordered = [...input.meters].sort(
      (left, right) => Number(left.value.length > WIDE_CHARS) - Number(right.value.length > WIDE_CHARS),
    );
    grid.replaceChildren(...ordered.map(readoutCell));
    body.replaceChildren(...input.peaks.map(peakRow));
  }

  return { root, update };
}
