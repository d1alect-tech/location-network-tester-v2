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

function buildOptions(style: SpectrumStyle, width: number): uPlot.Options {
  const axis = {
    stroke: style.axisText,
    grid: { stroke: style.grid, width: 1 },
    ticks: { stroke: style.grid, width: 1 },
    font: style.axisFont,
  };
  return {
    width,
    height: style.height,
    cursor: { drag: { setScale: true, x: true, y: false } },
    scales: {
      x: { time: false, distr: 3, log: 10, range: logRange },
      y: { time: false, distr: 3, log: 10, range: logRange },
    },
    series: [
      {},
      {
        label: "Сессия А",
        stroke: style.traceA,
        width: style.lineWidth,
        points: { show: false },
        spanGaps: true,
      },
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
      { ...axis, label: "PSD, В²/Гц" },
    ],
    legend: { show: false },
  };
}

/** Рисует график внутри host и добавляет легенду с двумя элементами [data-series]. */
export function renderSpectrum(
  host: HTMLElement,
  style: SpectrumStyle,
  labels: SpectrumLabels,
): void {
  host.textContent = "";
  const plotHost = document.createElement("div");
  plotHost.className = "spectrum-plot";
  const legend = document.createElement("div");
  legend.className = "spectrum-legend";
  const seriesA = document.createElement("span");
  seriesA.setAttribute("data-series", "a");
  seriesA.textContent = labels.a;
  const seriesB = document.createElement("span");
  seriesB.setAttribute("data-series", "b");
  seriesB.textContent = labels.b;
  legend.append(seriesA, seriesB);
  host.append(plotHost, legend);

  const plot = new uPlot(
    buildOptions(style, Math.max(plotHost.clientWidth, 320)),
    buildSpectrumData(),
    plotHost,
  );
  const observer = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry) return;
    const width = Math.floor(entry.contentRect.width);
    if (width > 0) {
      plot.setSize({ width, height: style.height });
    }
  });
  observer.observe(plotHost);
}
