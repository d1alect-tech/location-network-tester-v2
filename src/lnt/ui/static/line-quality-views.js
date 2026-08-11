// Панель качества сети 50 Гц: метрики трансформаторного входа CH1.
import {
  appendDataCell,
  appendTableHeader,
  element,
  numberText,
  valueText,
} from "./view-dom.js";

const TOP_HARMONICS = 8;

function metricsTable(metrics) {
  const table = element("table", "metrics-table");
  table.append(element("caption", "", "Качество сети 50 Гц (вторичка трансформатора)"));
  appendTableHeader(table, ["Метрика", "Значение", "Единица / смысл"]);
  const body = document.createElement("tbody");
  const rows = [
    ["Частота сети", numberText(metrics?.fundamental_hz), "Гц"],
    ["RMS фундаментала", numberText(metrics?.fundamental_rms_v), "В (вторичка)"],
    ["RMS полный", numberText(metrics?.total_rms_v), "В (вторичка)"],
    [
      "THD",
      typeof metrics?.thd_ratio === "number" ? `${numberText(metrics.thd_ratio * 100, 2)} %` : "н/д",
      "гармонические искажения H2+",
    ],
    ["Crest-factor", numberText(metrics?.crest_factor, 2), "пик/RMS; чистый синус = 1.41"],
    ["Огибающая CV", numberText(metrics?.envelope_cv, 4), "стабильность амплитуды"],
    ["Циклы", valueText(metrics?.cycles_analyzed), "шт."],
  ];
  for (const [name, value, meaning] of rows) {
    const row = document.createElement("tr");
    const heading = element("th", "", name);
    heading.scope = "row";
    row.append(heading);
    appendDataCell(row, value);
    appendDataCell(row, meaning);
    body.append(row);
  }
  table.append(body);
  return table;
}

function harmonicsTable(metrics) {
  const harmonics = element("table", "peaks-table harmonics-table");
  harmonics.append(element("caption", "", `Гармоники (топ-${TOP_HARMONICS} по уровню)`));
  appendTableHeader(harmonics, ["Гармоника", "Частота, Гц", "% от H1", "Амплитуда, В"]);
  const body = document.createElement("tbody");
  const items = Array.isArray(metrics?.harmonics) ? [...metrics.harmonics] : [];
  items.sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0));
  const top = items.slice(0, TOP_HARMONICS).sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  if (top.length === 0) {
    const row = document.createElement("tr");
    const cell = element("td", "", "Значимых гармоник не найдено");
    cell.colSpan = 4;
    row.append(cell);
    body.append(row);
  } else {
    for (const harmonic of top) {
      const row = document.createElement("tr");
      const heading = element("th", "", `H${valueText(harmonic.order)}`);
      heading.scope = "row";
      row.append(heading);
      appendDataCell(row, numberText(harmonic.frequency_hz, 1));
      appendDataCell(
        row,
        typeof harmonic.ratio === "number" ? numberText(harmonic.ratio * 100, 2) : "н/д",
      );
      appendDataCell(row, numberText(harmonic.amplitude_v, 3));
      body.append(row);
    }
  }
  harmonics.append(body);
  return harmonics;
}

export function renderLineQualityView(analysis) {
  const container = element("div", "analysis-content line-quality-content");
  container.append(metricsTable(analysis.line_quality), harmonicsTable(analysis.line_quality));
  return container;
}
