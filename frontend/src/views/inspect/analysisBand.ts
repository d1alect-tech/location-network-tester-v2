/** Лента анализа (G6, вариант «Два ряда»): ряд 1 — скаляры иглы и спектра
 * просторными плитками (модель и рендер — analysisMeters), ряд 2 — таблица
 * пиков с дельтой к базе (peaksTable) и Δ-полоса сбоку. Значения остаются
 * фактами: без нормативных слов.
 *
 * Задача 10 (D3): Δ пиков считается из пейлоадов ОТОБРАЖАЕМОЙ плоскости
 * (panel payloads, провод onPayloads) — той же, что график рядом; отдельного
 * scope-фетча для Δ больше нет. paintPeaksDelta перекрашивает дельты текущих
 * пик-строк из источника-плоскости; payload отсутствует — честное «—»
 * с причиной (словарь задачи 3), без scope-отката. */

import type { SpectrumPayload } from "../../api/types-plots";
import { el } from "../../components/primitives/dom";
import "./analysisBandReason.css";
import { type Meter, scalarCell } from "./analysisMeters";
import { createDeltaStrip } from "./deltaStrip";
import { type PeakRow, createPeaksTable } from "./peaksTable";

export type { Meter } from "./analysisMeters";
export type { PeakRow } from "./peaksTable";
export { EMPTY_METERS, metersFromDetail } from "./analysisMeters";

function heading(text: string, note: string): HTMLElement {
  return el("div", { className: "panel-hd" }, [
    el("h2", { className: "panel-title", text }),
    el("span", { className: "band-note", text: note }),
  ]);
}

export function createAnalysisBand(): {
  readonly root: HTMLElement;
  update(input: { meters: Meter[]; peaks: PeakRow[] }): void;
  paintDelta(a: SpectrumPayload | null, b: SpectrumPayload | null): void;
  /** Δ пиков из пейлоадов отображаемой плоскости (задача 10, D3). */
  paintPeaksDelta(
    a: SpectrumPayload | null,
    b: SpectrumPayload | null,
    reason?: string | null,
  ): void;
} {
  const deltaStrip = createDeltaStrip();
  const peaksTable = createPeaksTable();
  const grid = el("div", { className: "panel-bd band-scalars" });
  const rail = el("aside", { className: "band-rail", attrs: { "aria-label": "Δ-полоса" } }, [
    deltaStrip.root,
    el("p", {
      className: "band-rail-note",
      text: "Отсчёты вне ±8 дБ рисуются на границе диапазона.",
    }),
  ]);
  const root = el(
    "section",
    {
      className: "panel analysis-band",
      attrs: { "data-band-variant": "two-rows", "aria-label": "Лента анализа" },
    },
    [
      heading("Показания базы", "скаляры иглы и спектра"),
      grid,
      el("div", { className: "band-tier2" }, [peaksTable.root, rail]),
    ],
  );

  return {
    root,
    update(input) {
      grid.replaceChildren(...input.meters.map(scalarCell));
      peaksTable.update(input.peaks);
    },
    paintDelta(a, b) {
      deltaStrip.paint(a, b);
    },
    paintPeaksDelta(a, b, reason) {
      peaksTable.paintDelta(a, b, reason);
    },
  };
}
