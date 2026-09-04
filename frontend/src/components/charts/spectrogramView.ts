/** ECharts-вью спектрограммы (todo 42): heatmap-тайл из модульной регистрации.
 * Домен осей строится ОДИН раз на уровень (setDomain); смена тайла — частичный
 * setOption: заменяются только данные серии и диапазон visualMap, оси и зумы
 * не пересоздаются. Ячейки переиспользуют пул кортежей — без аллокации сотен
 * тысяч массивов на рендер. DOM-маркеры событий поверх канвы (фокус/клик/aria). */

import { el } from "../primitives/dom";
import type { SpectrogramChart, SpectrogramChartOption } from "./echarts";
import { initSpectrogramChart } from "./echarts";
import type { SpectrogramLevel } from "./spectrogramModel";
import { SPECTROGRAM_PALETTE } from "./spectrogramPalette";
import { readChartTheme } from "./theme";

export interface TileRenderData {
  times: Float64Array;
  freqs: Float64Array;
  values: Float32Array;
}

export interface MarkerSpec {
  timeS: number;
  label: string;
}

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

function formatSeconds(value: number): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 4 });
}

type Cell = [number, number, number];

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
  const markerLayer = el("div", {
    className: "lnt-spec-markers",
    attrs: { "aria-hidden": "true" },
  });
  const root = el("div", { className: "lnt-spec-root" }, [chartHost, markerLayer]);

  let chart: SpectrogramChart | null = null;
  let domainTimes: Float64Array<ArrayBufferLike> = new Float64Array(0);
  let domainFreqs: Float64Array<ArrayBufferLike> = new Float64Array(0);
  let markers: readonly MarkerSpec[] = [];
  let selectedMarker = -1;
  /** Пул кортежей ячеек: растёт до максимума и переиспользуется между рендерами. */
  const cellPool: Cell[] = [];
  const windowCallbacks: Array<(t: number, t2: number, f: number, f2: number) => void> = [];
  const markerCallbacks: Array<(index: number) => void> = [];

  function ensureChart(): SpectrogramChart {
    if (chart !== null && !chart.isDisposed()) return chart;
    chart = initSpectrogramChart(chartHost);
    chart.on("datazoom", () => emitWindow());
    return chart;
  }

  function axisWindow(axisIndex: number, values: Float64Array): [number, number] {
    if (chart === null) return [values[0] ?? 0, values[values.length - 1] ?? 0];
    const option = chart.getOption() as SpectrogramChartOption;
    const rawZooms = option.dataZoom ?? [];
    const zoomList = Array.isArray(rawZooms) ? rawZooms : [rawZooms];
    // Пары идут в порядке объявления: x-зумы [0,1], y-зумы [2,3].
    const zoom = zoomList[axisIndex === 0 ? 0 : 2];
    const startValue = typeof zoom?.startValue === "number" ? zoom.startValue : 0;
    const rawEnd =
      typeof zoom?.endValue === "number" ? zoom.endValue + 1 : (values.length as number);
    const start = Math.min(Math.max(0, startValue), values.length);
    const end = Math.min(Math.max(start + 1, rawEnd), values.length);
    return [values[start] ?? values[0] ?? 0, values[end - 1] ?? values[values.length - 1] ?? 0];
  }

  function emitWindow(): void {
    if (chart === null || domainTimes.length === 0) return;
    const [tStart, tEnd] = axisWindow(0, domainTimes);
    const [fLow, fHigh] = axisWindow(1, domainFreqs);
    for (const callback of windowCallbacks) callback(tStart, tEnd, fLow, fHigh);
  }

  function repositionMarkers(): void {
    markerLayer.replaceChildren();
    if (chart === null || chart.isDisposed() || markers.length === 0) return;
    const width = chartHost.clientWidth;
    for (const [index, marker] of markers.entries()) {
      let nearest = 0;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (let index2 = 0; index2 < domainTimes.length; index2 += 1) {
        const distance = Math.abs((domainTimes[index2] as number) - marker.timeS);
        if (distance < bestDistance) {
          bestDistance = distance;
          nearest = index2;
        }
      }
      const pixel = chart.convertToPixel({ xAxisIndex: 0 }, nearest);
      if (typeof pixel !== "number" || pixel < 0 || pixel > width) continue;
      const button = el("button", {
        className: index === selectedMarker ? "lnt-spec-marker is-selected" : "lnt-spec-marker",
        attrs: { type: "button", title: marker.label },
      });
      button.style.left = `${pixel}px`;
      button.addEventListener("click", () => {
        selectedMarker = index;
        repositionMarkers();
        for (const callback of markerCallbacks) callback(index);
      });
      markerLayer.append(button);
    }
  }

  const observer =
    typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => {
          chart?.resize();
          repositionMarkers();
        });
  observer?.observe(chartHost);

  chartHost.addEventListener("keydown", (event) => {
    if (markers.length === 0 || !(event instanceof KeyboardEvent)) return;
    let next = selectedMarker;
    if (event.key === "ArrowRight") next = Math.min(markers.length - 1, selectedMarker + 1);
    else if (event.key === "ArrowLeft") next = Math.max(0, selectedMarker - 1);
    else return;
    event.preventDefault();
    handle.focusMarker(next);
    for (const callback of markerCallbacks) callback(next);
  });

  function baseOption(): SpectrogramChartOption {
    return {
      animation: false,
      tooltip: {
        trigger: "item",
        formatter: (parameters) => {
          const value = parameters as { data?: Cell };
          const point = value.data;
          if (point === undefined) return "";
          const time = domainTimes[point[0]] ?? 0;
          const hz = domainFreqs[point[1]] ?? 0;
          return `время ${formatSeconds(time)} с · ${formatSeconds(hz)} Гц · ${formatSeconds(point[2])} дБВ/Гц (отн. 1 В²/Гц)`;
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
        text: ["дБВ/Гц макс", "дБВ/Гц мин"],
        inRange: { color: [...SPECTROGRAM_PALETTE] },
      },
      series: [{ type: "heatmap", data: [] }],
    };
  }

  const handle: SpectrogramViewHandle = {
    root,
    setDomain(level) {
      domainTimes = level.timeS;
      domainFreqs = level.frequencyHz;
      ensureChart().setOption(baseOption(), { notMerge: true });
      repositionMarkers();
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
      const width = data.times.length;
      const height = data.freqs.length;
      const total = width * height;
      while (cellPool.length < total) cellPool.push([0, 0, 0]);
      for (let f = 0; f < height; f += 1) {
        const rowOffset = f * width;
        for (let t = 0; t < width; t += 1) {
          const cell = cellPool[rowOffset + t] as Cell;
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
      repositionMarkers();
    },
    setMarkers(value) {
      markers = value;
      selectedMarker = -1;
      repositionMarkers();
    },
    highlightMarker(index) {
      selectedMarker = index;
      repositionMarkers();
      const buttons = markerLayer.querySelectorAll("button");
      buttons[index]?.classList.add("is-selected");
    },
    focusMarker(index) {
      const button = markerLayer.querySelectorAll("button")[index];
      if (button === undefined || button === null) return false;
      handle.highlightMarker(index);
      button.focus();
      return true;
    },
    onMarkerActivate(cb) {
      markerCallbacks.push(cb);
    },
    onWindowChange(cb) {
      windowCallbacks.push(cb);
    },
    dispose() {
      observer?.disconnect();
      windowCallbacks.length = 0;
      markerCallbacks.length = 0;
      markers = [];
      cellPool.length = 0;
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
