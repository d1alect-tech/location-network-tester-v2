/** Таблица пиков с Δ к базе (выделена из analysisBand по политике
 * test_module_size — задача 10/D3). Δ считается ЗДЕСЬ из пейлоадов той же
 * плоскости, что отображает соседний график (panel payloads, провод
 * onPayloads): пик-строки рендерятся с Δ из update, затем перекрашиваются
 * из последнего источника — порядок update/paintDelta не важен. Математика —
 * peaksDelta.peakDeltas без изменений; семантика плоскостей не менялась
 * (source alignment only).
 *
 * Причина отсутствия Δ (payload выбранной плоскости отсутствует) — видимый
 * соседний узел span.band-cell-reason в шапке таблицы (паттерн задачи 9):
 * значение ячейки «—» байт-в-байт не меняется, причина НЕ живёт в td.delta. */

import type { SpectrumPayload } from "../../api/types-plots";
import { el } from "../../components/primitives/dom";
import { peakDeltas } from "./peaksDelta";

export type PeakRow = {
  readonly frequencyHz: number;
  readonly baseDb: number;
  readonly deltaDb: number | null;
  readonly prominenceDb: number;
  readonly q: number;
};

type DeltaSource = {
  readonly a: SpectrumPayload | null;
  readonly b: SpectrumPayload | null;
  readonly reason: string | null;
};

const FLAT_DB = 0.05;
const ruNumber = new Intl.NumberFormat("ru-RU");

function deltaCell(deltaDb: number | null): HTMLTableCellElement {
  if (deltaDb === null) {
    return el("td", { className: "num delta is-flat", text: "—" });
  }
  const flat = Math.abs(deltaDb) <= FLAT_DB;
  const glyph = flat ? "—" : deltaDb < 0 ? "▼" : "▲";
  const tone = flat ? "is-flat" : deltaDb < 0 ? "is-down" : "is-up";
  return el("td", { className: `num delta ${tone}`, attrs: { "data-delta": deltaDb.toFixed(2) } }, [
    el("span", {
      className: "delta-glyph",
      text: glyph,
      attrs: { "aria-hidden": "true" },
    }),
    document.createTextNode(Math.abs(deltaDb).toFixed(1)),
  ]);
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

function withDelta(peak: PeakRow, deltaDb: number | null): PeakRow {
  return { ...peak, deltaDb };
}

export type PeaksTableHandle = {
  readonly root: HTMLElement;
  update(peaks: readonly PeakRow[]): void;
  paintDelta(a: SpectrumPayload | null, b: SpectrumPayload | null, reason?: string | null): void;
};

export function createPeaksTable(): PeaksTableHandle {
  const body = el("tbody");
  const reasonEl = el("span", {
    className: "band-cell-reason",
    attrs: { "data-role": "band-reason" },
  });
  reasonEl.hidden = true;
  const root = el("section", { className: "band-peaks", attrs: { "aria-label": "Пики спектра" } }, [
    el("div", { className: "panel-hd" }, [
      el("h2", { className: "panel-title", text: "Пики спектра · дельта к базе" }),
      el("span", { className: "band-note", text: "Δ = Б − А, дБ" }),
      reasonEl,
    ]),
    el("div", { className: "tbl-wrap" }, [
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

  let lastPeaks: readonly PeakRow[] = [];
  let source: DeltaSource | null = null;

  function renderRows(peaks: readonly PeakRow[]): void {
    body.replaceChildren(...peaks.map(peakRow));
  }

  function applySource(): void {
    if (source === null) return;
    const { a, b, reason } = source;
    const deltas =
      a !== null && b !== null
        ? peakDeltas(a.frequency_hz, a.psd_v2_per_hz, b.psd_v2_per_hz, lastPeaks)
        : null;
    renderRows(
      lastPeaks.map((peak, index) =>
        withDelta(peak, deltas === null ? null : (deltas[index]?.deltaDb ?? null)),
      ),
    );
    // Причина видна только при честном отсутствии Δ (пейлоад плоскости
    // отсутствует); при живом Δ узла нет — значение не объясняется.
    const showReason = (a === null || b === null) && reason !== null;
    reasonEl.hidden = !showReason;
    if (showReason && reason !== null) {
      reasonEl.textContent = reason;
      reasonEl.setAttribute("title", reason);
    }
  }

  return {
    root,
    update(peaks) {
      lastPeaks = peaks;
      renderRows(peaks);
      applySource();
    },
    paintDelta(a, b, reason) {
      source = { a, b, reason: reason ?? null };
      applySource();
    },
  };
}
