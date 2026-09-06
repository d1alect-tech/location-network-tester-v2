/** ECharts-вью спектрограммы (todo 42): тонкая сборка поверх листьев.
 * Опции/зумы — spectrogramViewOption, пул ячеек — spectrogramTiles,
 * DOM-маркеры — spectrogramMarkers. Домен осей строится ОДИН раз на уровень. */

import { el } from "../primitives/dom";
import type { SpectrogramChart } from "./echarts";
import { initSpectrogramChart } from "./echarts";
import { createMarkerLayer } from "./spectrogramMarkers";
import type { MarkerSpec } from "./spectrogramMarkers";
import type { SpectrogramLevel } from "./spectrogramModel";
import { createTilePool } from "./spectrogramTiles";
import type { TileRenderData } from "./spectrogramTiles";
import { axisWindow, baseOption } from "./spectrogramViewOption";
import { readChartTheme } from "./theme";

export type { MarkerSpec } from "./spectrogramMarkers";
export type { TileRenderData } from "./spectrogramTiles";

export interface SpectrogramViewHandle {
  root: HTMLElement;
  /** Домен уровня: оси/зумы строятся один раз, тайлы только меняют данные. */
  setDomain(level: Pick<SpectrogramLevel, "timeS" | "frequencyHz">): void;
  /** Нативный зум в окно тайла без пересборки данных серии (быстрый путь). */
  applyWindow(t0: number, t1: number, f0: number, f1: number): void;
  renderTile(data: TileRenderData, minDb: number, maxDb: number): void;
  setMarkers(markers: readonly MarkerSpec[]): void;
  highlightMarker(index: number): void;
  focusMarker(index: number): boolean;
  onMarkerActivate(cb: (index: number) => void): void;
  /** Точное окно после brush/dataZoom в значениях времени/полосы. */
  onWindowChange(
    cb: (tStartS: number, tEndS: number, fLowHz: number, fHighHz: number) => void,
  ): void;
  dispose(): void;
}

export function createSpectrogramView(): SpectrogramViewHandle {
  const theme = readChartTheme();
  const chartHost = el("div", {
    className: "lnt-spec-chart",
    attrs: {
      tabindex: "0",
      role: "img",
      "aria-label": "спектрограмма записи",
    },
  });
  const markerLayer = createMarkerLayer();
  const tilePool = createTilePool();
  const root = el("div", { className: "lnt-spec-root" }, [chartHost, markerLayer.element]);

  let chart: SpectrogramChart | null = null;
  let domainTimes: Float64Array<ArrayBufferLike> = new Float64Array(0);
  let domainFreqs: Float64Array<ArrayBufferLike> = new Float64Array(0);
  const windowCallbacks: Array<(t: number, t2: number, f: number, f2: number) => void> = [];

  function ensureChart(): SpectrogramChart {
    if (chart !== null && !chart.isDisposed()) return chart;
    chart = initSpectrogramChart(chartHost);
    chart.on("datazoom", () => emitWindow());
    return chart;
  }

  function emitWindow(): void {
    if (chart === null || domainTimes.length === 0) return;
    const [tStart, tEnd] = axisWindow(chart, 0, domainTimes);
    const [fLow, fHigh] = axisWindow(chart, 1, domainFreqs);
    for (const callback of windowCallbacks) callback(tStart, tEnd, fLow, fHigh);
  }

  function reposition(): void {
    markerLayer.reposition(chart, chartHost, domainTimes);
  }

  const observer =
    typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => {
          chart?.resize();
          reposition();
        });
  observer?.observe(chartHost);

  markerLayer.attachKeyboard(chartHost);

  const handle: SpectrogramViewHandle = {
    root,
    setDomain(level) {
      domainTimes = level.timeS;
      domainFreqs = level.frequencyHz;
      ensureChart().setOption(baseOption(domainTimes, domainFreqs), { notMerge: true });
      reposition();
    },
    applyWindow(t0, t1, f0, f1) {
      if (chart === null || chart.isDisposed()) return;
      // Нативные dataZoom-действия ОДНИМ батчем: одна перерисовка канвы,
      // существующие элементы серии не пересоздаются.
      chart.dispatchAction({
        type: "dataZoom",
        batch: [
          { dataZoomIndex: 0, startValue: t0, endValue: t1 - 1 },
          { dataZoomIndex: 2, startValue: f0, endValue: f1 - 1 },
        ],
      });
    },
    renderTile(data, minDb, maxDb) {
      if (chart === null || chart.isDisposed()) return;
      tilePool.render(chart, data, minDb, maxDb);
      reposition();
    },
    setMarkers(value) {
      markerLayer.setMarkers(value);
      reposition();
    },
    highlightMarker(index) {
      markerLayer.highlightMarker(index);
    },
    focusMarker(index) {
      return markerLayer.focusMarker(index);
    },
    onMarkerActivate(cb) {
      markerLayer.onMarkerActivate(cb);
    },
    onWindowChange(cb) {
      windowCallbacks.push(cb);
    },
    dispose() {
      observer?.disconnect();
      windowCallbacks.length = 0;
      markerLayer.dispose();
      tilePool.dispose();
      domainTimes = new Float64Array(0);
      domainFreqs = new Float64Array(0);
      chart?.dispose();
      chart = null;
      root.remove();
    },
  };

  // Подложка канвы использует токен панели; оси — вторичный текст DESIGN.md.
  chartHost.style.backgroundColor = theme.panel;

  return handle;
}
