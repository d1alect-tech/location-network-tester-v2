/** Раунд 2: метрики анализа и таблица пиков спектра (§1.4). */
import { METRICS, PEAKS } from "../showcase-redesign/data";
import { type KpiItem, h } from "./kit";

const ruNumber = new Intl.NumberFormat("ru-RU");

/** Показания из реального metrics.json: значение моно 600, единица 400 вторичным (§2.2). */
export const METERS: readonly KpiItem[] = [
  { label: "Частота сети", value: METRICS.lineFrequencyHz.toFixed(7), unit: "Гц" },
  { label: "μ иглы", value: METRICS.needleMeanV.toFixed(4), unit: "В" },
  { label: "σ/μ", value: METRICS.sigmaRatio.toFixed(3) },
  { label: "P_async/P_sync", value: METRICS.asyncSyncRatio.toFixed(2) },
  { label: "Циклов", value: String(METRICS.cyclesAnalyzed) },
  {
    label: "Полоса",
    value: `${ruNumber.format(METRICS.bandLowHz)}–${ruNumber.format(METRICS.bandHighHz)}`,
    unit: "Гц",
  },
  { label: "Разрешение", value: `${METRICS.resolutionHz}`, unit: "Гц" },
];

/** Панель «Показания»: сетка метрик + таблица пиков (f0, уровень, выделенность, Q). */
export function buildMetrics(): HTMLElement {
  const meterGrid = h("div", "meter-grid");
  for (const meter of METERS) {
    const value = h("span", "meter-value", {}, [meter.value]);
    if (meter.unit) value.append(h("span", "t-unit", {}, [meter.unit]));
    meterGrid.append(h("div", "meter", {}, [h("span", "meter-label", {}, [meter.label]), value]));
  }

  const peakBody = h("tbody");
  for (const peak of PEAKS) {
    peakBody.append(
      h("tr", "", {}, [
        h("td", "num", {}, [ruNumber.format(Math.round(peak.frequencyHz))]),
        h("td", "num", {}, [peak.levelDb.toFixed(2)]),
        h("td", "num", {}, [peak.prominenceDb.toFixed(2)]),
        h("td", "num", {}, [peak.q.toFixed(2)]),
      ]),
    );
  }

  return h("section", "panel", { "data-showcase": "metrics" }, [
    h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Показания"])]),
    h("div", "panel-bd", {}, [
      meterGrid,
      h("h3", "panel-title peaks-title", {}, ["Пики спектра"]),
      h("div", "tbl-wrap", {}, [
        h("table", "tbl tbl-tight", {}, [
          h("thead", "", {}, [
            h("tr", "", {}, [
              h("th", "", { scope: "col" }, ["f0, Гц"]),
              h("th", "", { scope: "col" }, ["Уровень, дБ"]),
              h("th", "", { scope: "col" }, ["Выдел., дБ"]),
              h("th", "", { scope: "col" }, ["Q"]),
            ]),
          ]),
          peakBody,
        ]),
      ]),
    ]),
  ]);
}
