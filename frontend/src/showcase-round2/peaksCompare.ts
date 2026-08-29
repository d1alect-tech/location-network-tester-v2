/** Таблица пиков с колонкой дельты (V6): к фиксированным колонкам §1.4 добавлена
 *  разница между трассами. Направление кодируется глифом ▲/▼/—, а не только цветом (§6). */
import { PEAKS } from "../showcase-redesign/data";
import { type PeakDelta, buildPeakDeltas } from "./deltas";
import { h } from "./kit";

const ruNumber = new Intl.NumberFormat("ru-RU");
/** Прочерк ставим только при фактическом нуле: десятые доли дБ — это измеренная разница,
 *  выдавать её за «без изменений» нельзя. */
const FLAT_DB = 0.05;

function deltaCell(delta: PeakDelta): HTMLElement {
  const flat = Math.abs(delta.deltaDb) < FLAT_DB;
  const glyph = flat ? "—" : delta.deltaDb < 0 ? "▼" : "▲";
  const tone = flat ? "is-flat" : delta.deltaDb < 0 ? "is-down" : "is-up";
  return h("td", `num delta ${tone}`, { "data-delta": delta.deltaDb.toFixed(2) }, [
    h("span", "delta-glyph", { "aria-hidden": "true" }, [glyph]),
    `${Math.abs(delta.deltaDb).toFixed(1)}`,
  ]);
}

export function buildPeaksCompare(): HTMLElement {
  const deltas = buildPeakDeltas();
  const body = h("tbody");
  PEAKS.forEach((peak, index) => {
    const delta = deltas[index];
    body.append(
      h("tr", "", { "data-peak-row": String(index), tabindex: "0" }, [
        h("td", "num", {}, [ruNumber.format(Math.round(peak.frequencyHz))]),
        h("td", "num", {}, [peak.levelDb.toFixed(2)]),
        delta === undefined ? h("td", "num delta is-flat", {}, ["—"]) : deltaCell(delta),
        h("td", "num", {}, [peak.prominenceDb.toFixed(2)]),
        h("td", "num", {}, [peak.q.toFixed(2)]),
      ]),
    );
  });
  return h("div", "tbl-wrap", {}, [
    h("table", "tbl tbl-tight tbl-peaks tbl-compare", {}, [
      h("thead", "", {}, [
        h("tr", "", {}, [
          h("th", "", { scope: "col" }, ["f0, Гц"]),
          h("th", "", { scope: "col" }, ["База, дБ"]),
          h("th", "", { scope: "col" }, ["Δ Б−А, дБ"]),
          h("th", "", { scope: "col" }, ["Выдел., дБ"]),
          h("th", "", { scope: "col" }, ["Q"]),
        ]),
      ]),
      body,
    ]),
  ]);
}
