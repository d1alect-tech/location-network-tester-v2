/** Чистый строитель опций спектрограммы (C0): formatSeconds/axisWindow/baseOption
 * вынесены из spectrogramView.ts без изменения байтов — visualMap/палитра
 * зафиксированы характеризационными снимками. Лист без обратного импорта вью. */

import type { SpectrogramChart, SpectrogramChartOption } from "./echarts";
import { SPECTROGRAM_PALETTE } from "./spectrogramPalette";

export type SpectrogramCell = [number, number, number];

export function formatSeconds(value: number): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 4 });
}

export function axisWindow(
  chart: SpectrogramChart | null,
  axisIndex: number,
  values: Float64Array,
): [number, number] {
  if (chart === null) return [values[0] ?? 0, values[values.length - 1] ?? 0];
  const option = chart.getOption() as SpectrogramChartOption;
  const rawZooms = option.dataZoom ?? [];
  const zoomList = Array.isArray(rawZooms) ? rawZooms : [rawZooms];
  // Пары идут в порядке объявления: x-зумы [0,1], y-зумы [2,3].
  const zoom = zoomList[axisIndex === 0 ? 0 : 2];
  const startValue = typeof zoom?.startValue === "number" ? zoom.startValue : 0;
  const rawEnd = typeof zoom?.endValue === "number" ? zoom.endValue + 1 : (values.length as number);
  const start = Math.min(Math.max(0, startValue), values.length);
  const end = Math.min(Math.max(start + 1, rawEnd), values.length);
  return [values[start] ?? values[0] ?? 0, values[end - 1] ?? values[values.length - 1] ?? 0];
}

export function baseOption(
  domainTimes: Float64Array<ArrayBufferLike>,
  domainFreqs: Float64Array<ArrayBufferLike>,
): SpectrogramChartOption {
  return {
    animation: false,
    tooltip: {
      trigger: "item",
      formatter: (parameters) => {
        const value = parameters as { data?: SpectrogramCell };
        const point = value.data;
        if (point === undefined) return "";
        const time = domainTimes[point[0]] ?? 0;
        const hz = domainFreqs[point[1]] ?? 0;
        return `время ${formatSeconds(time)} с · ${formatSeconds(hz)} Гц · ${formatSeconds(point[2])} дБ`;
      },
    },
    grid: { left: 64, right: 84, top: 16, bottom: 56 },
    xAxis: { type: "category", data: Array.from(domainTimes, formatSeconds), name: "Время, с" },
    yAxis: {
      type: "category",
      data: Array.from(domainFreqs, formatSeconds),
      name: "Частота, Гц",
    },
    dataZoom: [
      { type: "inside", xAxisIndex: 0, filterMode: "weakFilter" },
      {
        type: "slider",
        xAxisIndex: 0,
        bottom: 8,
        startValue: 0,
        endValue: domainTimes.length - 1,
      },
      { type: "inside", yAxisIndex: 0, filterMode: "weakFilter" },
      {
        type: "slider",
        yAxisIndex: 0,
        right: 8,
        startValue: 0,
        endValue: domainFreqs.length - 1,
      },
    ],
    visualMap: {
      min: 0,
      max: 1,
      calculable: true,
      realtime: false,
      orient: "vertical",
      right: 4,
      top: "center",
      text: ["дБ макс", "дБ мин"],
      inRange: { color: [...SPECTROGRAM_PALETTE] },
    },
    series: [{ type: "heatmap", data: [] }],
  };
}
