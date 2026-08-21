/** uPlot-реализация ChartHandle (todo 41): монтирование в контейнер,
 * выравнивание рядов, log-safe фильтрация, ResizeObserver, темы.
 * Синхронизация курсора/диапазонов — общая sync-группа uplotOptions. */

import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { readChartTheme } from "./theme";
import type { ChartHandle, ChartRenderRequest } from "./types";
import { buildUplotOptions } from "./uplotOptions";

export interface UplotViewOptions {
  container: HTMLElement;
  syncKey: string;
  onCursor?: (index: number | null) => void;
  /** Плагин аннотаций пиков/полос. */
  peaksPlugin?: uPlot.Plugin;
}

/** Совместная очистка X и всех серий: индекс с невалидной координатой
 * хотя бы одного ряда отбрасывается у всех — выравнивание сохраняется. */
function prepareAligned(request: ChartRenderRequest): uPlot.AlignedData {
  const columns: number[][] = [[...request.x], ...request.series.map((entry) => [...entry.values])];
  const width = Math.min(...columns.map((column) => column.length));
  if (!Number.isFinite(width)) return [[], []];
  const keepX: number[] = [];
  const keepColumns: number[][] = columns.map(() => []);
  for (let i = 0; i < width; i += 1) {
    const xValue = request.x[i];
    let allValid =
      xValue !== undefined && Number.isFinite(xValue) && (request.xLog !== true || xValue > 0);
    for (const column of columns) {
      const value = column[i];
      if (value === undefined || !Number.isFinite(value) || (request.yLog === true && value <= 0)) {
        allValid = false;
        break;
      }
    }
    if (!allValid || xValue === undefined) continue;
    for (let c = 0; c < columns.length; c += 1) {
      const value = columns[c]?.[i];
      const target = keepColumns[c];
      if (value !== undefined && target !== undefined) target.push(value);
    }
    keepX.push(xValue);
  }
  return [keepX, ...keepColumns.slice(1)];
}

export function createUplotView(options: UplotViewOptions): ChartHandle {
  let theme = readChartTheme();
  let plot: uPlot | null = null;
  let lastRequest: ChartRenderRequest | null = null;
  let host: HTMLDivElement | null = null;

  function ensureHost(): HTMLDivElement {
    if (host?.isConnected === true) return host;
    host?.remove();
    host = document.createElement("div");
    host.className = "lnt-uplot-host";
    options.container.append(host);
    return host;
  }

  function emitCursor(self: uPlot): void {
    options.onCursor?.(self.cursor.idx ?? null);
  }

  function draw(width: number, height: number): void {
    if (lastRequest === null || width <= 0 || height <= 0) return;
    const target = ensureHost();
    target.replaceChildren();
    plot?.destroy();
    const aligned = prepareAligned(lastRequest);
    plot = new uPlot(
      buildUplotOptions({
        request: lastRequest,
        theme,
        width,
        height,
        syncKey: options.syncKey,
        onCursor: emitCursor,
        peaksPlugin: options.peaksPlugin,
      }),
      aligned,
      target,
    );
  }

  const observer =
    typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver((entries) => {
          const box = entries.at(-1)?.contentRect;
          if (box === undefined) return;
          draw(Math.floor(box.width), Math.floor(box.height));
        });

  const root = document.createElement("div");
  root.className = "lnt-uplot-root";

  return {
    root,
    render(request) {
      lastRequest = request;
      draw(options.container.clientWidth, options.container.clientHeight);
      observer?.observe(options.container);
    },
    applyTheme() {
      theme = readChartTheme();
      const previous = plot;
      if (previous === null || lastRequest === null) return;
      const scaleState = previous.scales.x;
      const min = scaleState?.min;
      const max = scaleState?.max;
      draw(options.container.clientWidth, options.container.clientHeight);
      if (typeof min === "number" && typeof max === "number" && plot !== null) {
        plot.setScale("x", { min, max });
      }
    },
    getData: () => plot?.data ?? null,
    destroy() {
      observer?.disconnect();
      plot?.destroy();
      plot = null;
      host?.remove();
      host = null;
      lastRequest = null;
    },
  };
}
