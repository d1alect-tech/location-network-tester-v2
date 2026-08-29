/** Общий рендерер спектра для всех витрин: uPlot, лог-лог оси, две трассы A/B.
 *  Варианты дизайна стилизуют график через объект стиля и CSS-переменные. */
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

export interface SpectrumStyle {
  traceA: string;
  traceB: string;
  grid: string;
  axisText: string;
  lineWidth: number;
  /** Штрих трассы Б: различие А/Б должно читаться без цвета. */
  dash: number[];
  axisFont: string;
  height: number;
}

export interface SpectrumLabels {
  a: string;
  b: string;
}

export interface SpectrumChrome {
  readonly header: HTMLElement;
}

type PlotExtras = {
  readonly ticksStroke: string;
  readonly fillA?: string;
  readonly onCursor?: (u: uPlot) => void;
};

/** Детерминированный PSD: шумовой пол + гауссовы пики; трасса Б ниже А на ~12 дБ у 22.4 кГц. */
export function buildSpectrumData(): uPlot.AlignedData {
  const n = 1000;
  const f0 = 3000;
  const f1 = 3000000;
  const freq = new Float64Array(n);
  const psdA = new Float64Array(n);
  const psdB = new Float64Array(n);
  const peak = (f: number, amp: number, fc: number, width: number): number =>
    amp * Math.exp(-(((f - fc) / width) ** 2));
  for (let i = 0; i < n; i++) {
    const f = f0 * (f1 / f0) ** (i / (n - 1));
    freq[i] = f;
    const floor = 4e-10 * (f / f0) ** -0.35 * (1 + 0.06 * Math.sin(i / 7));
    psdA[i] =
      floor + peak(f, 2.2e-6, 22418, 420) + peak(f, 9e-7, 27440, 300) + peak(f, 4e-7, 32457, 260);
    psdB[i] =
      floor +
      peak(f, 5.5e-7, 22418, 420) +
      peak(f, 8.2e-7, 27440, 300) +
      peak(f, 4.1e-7, 32457, 260);
  }
  return [freq, psdA, psdB];
}

function logRange(_self: uPlot, initMin: number, initMax: number) {
  return uPlot.rangeLog(initMin, initMax, 10, true);
}

function chromePlotStyle(style: SpectrumStyle): SpectrumStyle {
  return {
    ...style,
    lineWidth: 2,
    grid: "rgba(255,255,255,0.08)",
    axisText: "#8E8E8E",
    axisFont: '500 10px "JetBrains Mono Variable", monospace',
  };
}

function sampleAt(column: uPlot.AlignedData[number] | undefined, idx: number): number | undefined {
  if (column === undefined) return undefined;
  const value = column[idx];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function formatReadout(u: uPlot, idx: number | null): string {
  if (idx == null) return "наведите на график";
  const f = sampleAt(u.data[0], idx);
  const a = sampleAt(u.data[1], idx);
  const b = sampleAt(u.data[2], idx);
  if (f === undefined || a === undefined || b === undefined || !(a > 0) || !(b > 0)) {
    return "наведите на график";
  }
  const fStr =
    f >= 1000
      ? `${(f / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} кГц`
      : `${Math.round(f)} Гц`;
  const aStr = (10 * Math.log10(a)).toFixed(1);
  const bStr = (10 * Math.log10(b)).toFixed(1);
  return `f ${fStr} · A ${aStr} дБ · B ${bStr} дБ`;
}

function appendChip(
  parent: HTMLElement,
  series: "a" | "b",
  swatchKind: "solid" | "dash",
  label: string,
): void {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "chip";
  chip.setAttribute("data-series", series);
  const swatch = document.createElement("span");
  swatch.className = `swatch swatch-${swatchKind}`;
  swatch.setAttribute("data-swatch", swatchKind);
  const text = document.createElement("span");
  text.textContent = label;
  chip.append(swatch, text);
  parent.append(chip);
}

function mountChrome(header: HTMLElement, labels: SpectrumLabels): HTMLElement {
  const chips = document.createElement("div");
  chips.className = "spectrum-chips";
  appendChip(chips, "a", "solid", `● ${labels.a}`);
  appendChip(chips, "b", "dash", `■ ${labels.b}`);
  const readout = document.createElement("span");
  readout.className = "spectrum-readout";
  readout.setAttribute("data-readout", "");
  readout.textContent = "наведите на график";
  header.append(chips, readout);
  return readout;
}

function buildLegend(labels: SpectrumLabels): HTMLElement {
  const legend = document.createElement("div");
  legend.className = "spectrum-legend";
  const seriesA = document.createElement("span");
  seriesA.setAttribute("data-series", "a");
  seriesA.textContent = labels.a;
  const seriesB = document.createElement("span");
  seriesB.setAttribute("data-series", "b");
  seriesB.textContent = labels.b;
  legend.append(seriesA, seriesB);
  return legend;
}

function buildOptions(style: SpectrumStyle, width: number, extras: PlotExtras): uPlot.Options {
  const axis = {
    stroke: style.axisText,
    grid: { stroke: style.grid, width: 1 },
    ticks: { stroke: extras.ticksStroke, width: 1 },
    font: style.axisFont,
  };
  const seriesA: uPlot.Series = {
    label: "Сессия А",
    stroke: style.traceA,
    width: style.lineWidth,
    points: { show: false },
    spanGaps: true,
  };
  if (extras.fillA !== undefined) {
    seriesA.fill = extras.fillA;
  }
  const options: uPlot.Options = {
    width,
    height: style.height,
    cursor: { drag: { setScale: true, x: true, y: false } },
    scales: {
      x: { time: false, distr: 3, log: 10, range: logRange },
      y: { time: false, distr: 3, log: 10, range: logRange },
    },
    series: [
      {},
      seriesA,
      {
        label: "Сессия Б",
        stroke: style.traceB,
        width: style.lineWidth,
        dash: style.dash,
        points: { show: false },
        spanGaps: true,
      },
    ],
    axes: [
      { ...axis, label: "Частота, Гц" },
      {
        ...axis,
        label: "PSD, В²/Гц",
        // Лог-шкала: порядок вместо «0» — деления должны читаться (§9.4).
        values: (_u: uPlot, ticks: (number | null)[]) =>
          ticks.map((tick) => (tick == null ? "" : tick.toExponential(0))),
      },
    ],
    legend: { show: false },
  };
  if (extras.onCursor !== undefined) {
    options.hooks = { setCursor: [extras.onCursor] };
  }
  return options;
}

/** Рисует график внутри host. Без chrome — нижняя легенда .spectrum-legend (раунд 1).
 *  С chrome — чипы и ридеут в header, нижней легенды нет. */
export function renderSpectrum(
  host: HTMLElement,
  style: SpectrumStyle,
  labels: SpectrumLabels,
  chrome?: SpectrumChrome,
): void {
  host.textContent = "";
  const plotHost = document.createElement("div");
  plotHost.className = "spectrum-plot";
  host.append(plotHost);

  let extras: PlotExtras = { ticksStroke: style.grid };
  let plotStyle = style;
  if (chrome !== undefined) {
    const readout = mountChrome(chrome.header, labels);
    plotStyle = chromePlotStyle(style);
    extras = {
      ticksStroke: "rgba(255,255,255,0.15)",
      fillA: "rgba(86,129,255,0.12)",
      onCursor: (u: uPlot) => {
        readout.textContent = formatReadout(u, u.cursor.idx ?? null);
      },
    };
  } else {
    host.append(buildLegend(labels));
  }

  const plot = new uPlot(
    buildOptions(plotStyle, Math.max(plotHost.clientWidth, 320), extras),
    buildSpectrumData(),
    plotHost,
  );
  let lastWidth = 0;
  const observer = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry) return;
    const width = Math.floor(entry.contentRect.width);
    if (width > 0 && width !== lastWidth) {
      lastWidth = width;
      plot.setSize({ width, height: plotStyle.height });
    }
  });
  observer.observe(plotHost);
}
