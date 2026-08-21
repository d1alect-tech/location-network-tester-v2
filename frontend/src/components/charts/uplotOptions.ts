/** Сборка опций uPlot из рендер-запроса и дизайн-токенов (todo 41).
 * Лог-оси: distr=3 с rangeLog; синхронизация курсора и диапазонов X —
 * общая sync-группа со шкалой по значениям ("x") и относительной Y. */

import uPlot from "uplot";
import type { ChartTheme } from "./theme";
import type { ChartRenderRequest } from "./types";

export interface UplotBuildContext {
  request: ChartRenderRequest;
  theme: ChartTheme;
  width: number;
  height: number;
  syncKey: string;
  /** Вызывается при движении курсора (локальном и синхронизированном). */
  onCursor: (self: uPlot) => void;
  /** Плагин аннотаций пиков/полос (может отсутствовать). */
  peaksPlugin?: uPlot.Plugin;
}

const LOG_RANGE: uPlot.Range.Function = (_self, initMin, initMax) =>
  uPlot.rangeLog(initMin, initMax, 10, true);

function axis(label: string, theme: ChartTheme): uPlot.Axis {
  return {
    label,
    stroke: theme.fgSecondary,
    grid: { stroke: theme.borderSubtle, width: theme.lineWidth },
    ticks: { stroke: theme.borderSubtle, width: theme.lineWidth },
    font: `${12}px ${theme.fontMono}`,
    labelFont: `${13}px ${theme.fontSans}`,
  };
}

function scale(log: boolean | undefined): uPlot.Scale {
  if (!log) return { time: false };
  return { time: false, distr: 3, log: 10, range: LOG_RANGE };
}

export function buildUplotOptions(ctx: UplotBuildContext): uPlot.Options {
  const { request, theme, width, height, syncKey } = ctx;
  const series: uPlot.Series[] = [{}];
  for (const entry of request.series) {
    series.push({
      label: entry.marker === undefined ? entry.label : `${entry.marker} ${entry.label}`,
      stroke: entry.color,
      width: 1.5,
      dash: entry.dash === undefined ? undefined : [...entry.dash],
      points: { show: false },
      spanGaps: true,
    });
  }

  const options: uPlot.Options = {
    width,
    height,
    class: "lnt-uplot",
    series,
    scales: { x: scale(request.xLog), y: scale(request.yLog) },
    axes: [axis(request.xLabel, theme), axis(request.yLabel, theme)],
    legend: {
      show: true,
      live: true,
      markers: {
        show: true,
        // Нецветовая метка Б: пунктирный маркер легенды (DESIGN.md 4.2).
        dash: (_self, seriesIdx) =>
          request.series[seriesIdx - 1]?.dash !== undefined ? "dashed" : "solid",
      },
    },
    cursor: {
      sync: { key: syncKey, scales: ["x", null] },
      drag: { setScale: true, x: true, y: false },
    },
    hooks: { setCursor: [ctx.onCursor] },
  };
  if (ctx.peaksPlugin !== undefined) options.plugins = [ctx.peaksPlugin];
  return options;
}
