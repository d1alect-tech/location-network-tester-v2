/** Ориентированная спектрограмма записи: частота по X, время по Y
 * (верх = начало записи). Оси — category по бинам npz; DOM-оверлей тиков
 * частоты не строится (это отдельная задача). Пул ячеек + кап TILE_CELL_CAP. */

import type { SpectrogramChart, SpectrogramChartOption } from "../../components/charts/echarts";
import { initSpectrogramChart } from "../../components/charts/echarts";
import type { SpectrogramLevel } from "../../components/charts/spectrogramModel";
import { TILE_CELL_CAP } from "../../components/charts/spectrogramModel";
import { SPECTROGRAM_PALETTE } from "../../components/charts/spectrogramPalette";
import { readChartTheme } from "../../components/charts/theme";
import { el } from "../../components/primitives/dom";

export type OrientedSpectrogramTile = {
  readonly times: Float64Array;
  readonly freqs: Float64Array;
  readonly values: Float32Array;
};

export type OrientedSpectrogramView = {
  readonly root: HTMLElement;
  setDomain(level: Pick<SpectrogramLevel, "timeS" | "frequencyHz">): void;
  renderTile(data: OrientedSpectrogramTile, minDb: number, maxDb: number): void;
  dispose(): void;
};

/** Injectable chart surface: production `initSpectrogramChart` satisfies this. */
export type OrientedChart = Pick<SpectrogramChart, "setOption" | "resize" | "dispose">;

export type OrientedSpectrogramOpts = {
  readonly init?: (host: HTMLElement) => OrientedChart;
};

type Cell = [number, number, number];

function formatNumber(value: number): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 4 });
}

function tooltipCell(parameters: unknown): Cell | undefined {
  if (typeof parameters !== "object" || parameters === null) return undefined;
  if (!("data" in parameters)) return undefined;
  const data = parameters.data;
  if (!Array.isArray(data) || data.length < 3) return undefined;
  const freqIndex = data[0];
  const timeIndex = data[1];
  const db = data[2];
  if (typeof freqIndex !== "number" || typeof timeIndex !== "number" || typeof db !== "number") {
    return undefined;
  }
  return [freqIndex, timeIndex, db];
}

export function createOrientedSpectrogramView(
  opts?: OrientedSpectrogramOpts,
): OrientedSpectrogramView {
  const theme = readChartTheme();
  const startChart = opts?.init ?? initSpectrogramChart;
  const host = el("div", {
    className: "lnt-spec-chart",
    attrs: {
      tabindex: "0",
      role: "img",
      "aria-label": "спектрограмма записи",
    },
  });
  const root = el("div", { className: "lnt-spec-root" }, [host]);
  host.style.backgroundColor = theme.panel;

  let chart: OrientedChart | null = null;
  let domainTimes: Float64Array<ArrayBufferLike> = new Float64Array(0);
  let domainFreqs: Float64Array<ArrayBufferLike> = new Float64Array(0);
  const cellPool: Cell[] = [];

  const observer =
    typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => {
          chart?.resize();
        });
  observer?.observe(host);

  function ensureChart(): OrientedChart {
    if (chart !== null) return chart;
    chart = startChart(host);
    return chart;
  }

  function baseOption(): SpectrogramChartOption {
    return {
      animation: false,
      tooltip: {
        trigger: "item",
        formatter: (parameters) => {
          const point = tooltipCell(parameters);
          if (point === undefined) return "";
          const hz = domainFreqs[point[0]] ?? 0;
          const time = domainTimes[point[1]] ?? 0;
          return `частота ${formatNumber(hz)} Гц · время ${formatNumber(time)} с · ${formatNumber(point[2])} дБВ/Гц (отн. 1 В²/Гц)`;
        },
      },
      grid: { left: 64, right: 84, top: 16, bottom: 56 },
      xAxis: {
        type: "category",
        data: Array.from(domainFreqs, formatNumber),
        name: "Частота, Гц",
      },
      yAxis: {
        type: "category",
        data: Array.from(domainTimes, formatNumber),
        name: "Время, с",
        inverse: true,
      },
      visualMap: {
        min: 0,
        max: 1,
        calculable: true,
        orient: "vertical",
        right: 4,
        top: "center",
        text: ["дБВ/Гц макс", "дБВ/Гц мин"],
        inRange: { color: [...SPECTROGRAM_PALETTE] },
      },
      series: [{ type: "heatmap", data: [] }],
    };
  }

  return {
    root,
    setDomain(level) {
      domainTimes = level.timeS;
      domainFreqs = level.frequencyHz;
      ensureChart().setOption(baseOption(), { notMerge: true });
    },
    renderTile(data, minDb, maxDb) {
      if (chart === null) return;
      const nTimes = data.times.length;
      const nFreqs = data.freqs.length;
      const total = Math.min(nTimes * nFreqs, TILE_CELL_CAP);
      while (cellPool.length < total) cellPool.push([0, 0, 0]);
      let written = 0;
      for (let f = 0; f < nFreqs && written < total; f += 1) {
        const rowOffset = f * nTimes;
        for (let t = 0; t < nTimes && written < total; t += 1) {
          const cell = cellPool[written];
          if (cell === undefined) break;
          cell[0] = f;
          cell[1] = t;
          cell[2] = data.values[rowOffset + t] ?? 0;
          written += 1;
        }
      }
      chart.setOption({
        series: [{ type: "heatmap", data: cellPool.slice(0, written) }],
        visualMap: { min: minDb, max: maxDb },
      });
    },
    dispose() {
      observer?.disconnect();
      cellPool.length = 0;
      domainTimes = new Float64Array(0);
      domainFreqs = new Float64Array(0);
      chart?.dispose();
      chart = null;
    },
  };
}
