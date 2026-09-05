/** Пул ячеек heatmap-тайла спектрограммы (C1-лист): переиспользование кортежей
 * без аллокации сотен тысяч массивов на рендер + частичный setOption
 * (только данные серии и диапазон visualMap) — вынесены из spectrogramView.ts
 * без изменения байтов, поверх C0 spectrogramViewOption.ts. Лист без
 * обратного импорта вью. */

import type { SpectrogramChart } from "./echarts";
import type { SpectrogramCell } from "./spectrogramViewOption";

export interface TileRenderData {
  times: Float64Array;
  freqs: Float64Array;
  values: Float32Array;
}

export interface TilePoolHandle {
  render(chart: SpectrogramChart | null, data: TileRenderData, minDb: number, maxDb: number): void;
  dispose(): void;
}

export function createTilePool(): TilePoolHandle {
  /** Пул кортежей ячеек: растёт до максимума и переиспользуется между рендерами. */
  const cellPool: SpectrogramCell[] = [];

  function render(
    chart: SpectrogramChart | null,
    data: TileRenderData,
    minDb: number,
    maxDb: number,
  ): void {
    if (chart === null || chart.isDisposed()) return;
    const width = data.times.length;
    const height = data.freqs.length;
    const total = width * height;
    while (cellPool.length < total) cellPool.push([0, 0, 0]);
    for (let f = 0; f < height; f += 1) {
      const rowOffset = f * width;
      for (let t = 0; t < width; t += 1) {
        const cell = cellPool[rowOffset + t] as SpectrogramCell;
        cell[0] = t;
        cell[1] = f;
        cell[2] = data.values[rowOffset + t] as number;
      }
    }
    // Частичный апдейт: оси/зумы/подписи не пересоздаются.
    chart.setOption({
      series: [{ type: "heatmap", data: cellPool.slice(0, total) }],
      visualMap: { min: minDb, max: maxDb },
    });
  }

  function dispose(): void {
    cellPool.length = 0;
  }

  return { render, dispose };
}
