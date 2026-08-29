/** Маркеры пиков поверх области спектра (V5): вертикальная риска с подписью частоты,
 *  связанная со строкой таблицы пиков. Слой лежит в plot.over и не перехватывает
 *  указатель — родной курсор и drag-зум uPlot остаются рабочими.
 *
 *  Координата приходит из шкалы графика, но в разметку не попадает: позиции
 *  публикуются правилами конструируемого стиль-листа по классу и атрибуту,
 *  поэтому в DOM нет ни одного inline-стиля (§2.5, §7). */
import type uPlot from "uplot";
import { PEAKS } from "../showcase-redesign/data";

const KHZ = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

/** Номер пика виден всегда, частота — при подсветке: на лог-шкале соседние
 *  пики 22.4/27.4/32.5 кГц разведены на ~26px и полные подписи наложились бы. */
function buildMark(index: number, frequencyHz: number): HTMLElement {
  const mark = document.createElement("div");
  mark.className = "peak-mark";
  mark.setAttribute("data-peak", String(index));
  const ordinal = document.createElement("span");
  ordinal.className = "peak-mark-index";
  ordinal.textContent = String(index + 1);
  const label = document.createElement("span");
  label.className = "peak-mark-label";
  label.textContent = `${KHZ.format(frequencyHz / 1000)} кГц`;
  mark.append(ordinal, label);
  return mark;
}

function bindRow(row: HTMLElement, mark: HTMLElement): void {
  const setHot = (hot: boolean): void => {
    mark.classList.toggle("is-hot", hot);
    row.classList.toggle("is-hot", hot);
  };
  row.addEventListener("mouseenter", () => setHot(true));
  row.addEventListener("mouseleave", () => setHot(false));
  row.addEventListener("focus", () => setHot(true));
  row.addEventListener("blur", () => setHot(false));
}

/** Монтирует слой маркеров и возвращает функцию пересчёта позиций (зум, ресайз). */
export function mountPeakMarkers(plot: uPlot, rows: readonly HTMLElement[]): () => void {
  const layer = document.createElement("div");
  layer.className = "peak-layer";
  const marks = PEAKS.map((peak, index) => {
    const mark = buildMark(index, peak.frequencyHz);
    layer.append(mark);
    return mark;
  });
  plot.over.append(layer);

  rows.forEach((row, index) => {
    const mark = marks[index];
    if (mark !== undefined) bindRow(row, mark);
  });

  const sheet = new CSSStyleSheet();
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];

  const place = (): void => {
    const width = plot.over.clientWidth;
    const rules: string[] = [];
    PEAKS.forEach((peak, index) => {
      const mark = marks[index];
      if (mark === undefined) return;
      const x = plot.valToPos(peak.frequencyHz, "x");
      const visible = Number.isFinite(x) && x >= 0 && x <= width;
      mark.classList.toggle("is-off", !visible);
      rules.push(`.peak-mark[data-peak="${index}"] { left: ${Math.round(x)}px; }`);
    });
    sheet.replaceSync(rules.join("\n"));
  };
  place();
  return place;
}
