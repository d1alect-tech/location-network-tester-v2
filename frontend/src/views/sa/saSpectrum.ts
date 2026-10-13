/** Живой спектр SA (Todo 14): трассы склада общим стеком uPlot
 * (createUplotView, второй стек не заводится). Сервер уже проредил трассу
 * до ≤ 5000 точек — клиентского прореживания нет, исходники склада не
 * мутируются (перевод единиц — в копию ряда). Ось X фиксирована сеткой
 * полосы (линейная по умолчанию, лог — опция: prepareAligned отбрасывает
 * f≤0), ось Y — авто. Ожидание/отказ свипа — видимый статус. */

import { readChartTheme } from "../../components/charts/theme";
import type { ChartTheme } from "../../components/charts/theme";
import type { ChartRenderRequest, ChartRenderSeries } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import { el } from "../../components/primitives/dom";
import type { SaTraceKind, SaTraceStore } from "./saTraceStore";
import { type SaDisplayUnit, saLevelToDisplay, saYAxisLabel } from "./saUnits";
import "./sa.css";

const SYNC_KEY = "lnt-sa-spectrum";
const DASH_HOLD: readonly [number, number] = [2, 3];
const DASH_AVG: readonly [number, number] = [6, 4];

export interface SaSpectrumViewOptions {
  unit: SaDisplayUnit;
  xLog: boolean;
  traces: ReadonlySet<SaTraceKind>;
}

export interface SaSpectrumOptions {
  /** Тестовый шов (паттерн scopeWaveform): фабрика хэндла графика. */
  createView?: typeof createUplotView;
  /** Узел управления трассами (saTraceControls) над графиком. */
  controls?: Node;
}

export interface SaSpectrumHandle {
  readonly root: HTMLElement;
  /** Рендер склада под текущие опции отображения (вызов на свип). */
  applyStore(store: SaTraceStore, options: SaSpectrumViewOptions): void;
  /** Перерисовка последнего склада под новые опции (единицы/шкала/вид). */
  rerender(options: SaSpectrumViewOptions): void;
  /** Свип отклонён складом: статус виден, прошлый рендер остаётся. */
  showProblem(): void;
  destroy(): void;
}

function seriesStyle(
  kind: SaTraceKind,
  values: readonly number[],
  theme: ChartTheme,
): ChartRenderSeries {
  const labels: Record<SaTraceKind, string> = {
    clear: "Трасса",
    max: "Max-hold",
    min: "Min-hold",
    avg: "Среднее",
  };
  const base = { label: labels[kind], values };
  if (kind === "clear") return { ...base, color: theme.accentA };
  if (kind === "max") return { ...base, color: theme.accentB, dash: DASH_HOLD };
  if (kind === "min") return { ...base, color: theme.delta, dash: DASH_HOLD };
  return { ...base, color: theme.ok, dash: DASH_AVG };
}

export function mountSaSpectrum(options: SaSpectrumOptions = {}): SaSpectrumHandle {
  const factory = options.createView ?? createUplotView;
  const figure = el("div", { className: "lnt-sa-figure" });
  const status = el("p", {
    className: "lnt-sa-wave-status",
    text: "ожидание свипа…",
    attrs: { role: "status", "data-sa-wave-state": "waiting" },
  });
  const chart = factory({ container: figure, syncKey: SYNC_KEY });
  figure.append(chart.root);
  const bodyChildren: Node[] = [];
  if (options.controls !== undefined) bodyChildren.push(options.controls);
  bodyChildren.push(figure, status);
  const root = el("section", { className: "panel lnt-sa-section lnt-sa-wave" }, [
    el("div", { className: "panel-hd" }, [
      el("h3", { className: "panel-title", text: "Живой спектр" }),
    ]),
    el("div", { className: "panel-bd" }, bodyChildren),
  ]);
  let lastStore: SaTraceStore | null = null;

  function paintWaiting(): void {
    status.hidden = false;
    status.setAttribute("data-sa-wave-state", "waiting");
    status.textContent = "ожидание свипа…";
  }

  function paintRejected(): void {
    status.hidden = false;
    status.setAttribute("data-sa-wave-state", "problem");
    status.textContent = "свип отклонён: мусорный вход";
  }

  function render(store: SaTraceStore, view: SaSpectrumViewOptions): void {
    const freq = store.freq();
    if (freq === null) {
      paintWaiting();
      return;
    }
    status.hidden = true;
    status.setAttribute("data-sa-wave-state", "ok");
    const theme = readChartTheme();
    const kinds: SaTraceKind[] = ["clear", "max", "min", "avg"];
    const series: ChartRenderSeries[] = [];
    for (const kind of kinds) {
      if (!view.traces.has(kind)) continue;
      const trace = store.trace(kind);
      if (trace === null) continue;
      series.push(
        seriesStyle(
          kind,
          Array.from(trace, (level) => saLevelToDisplay(level, view.unit)),
          theme,
        ),
      );
    }
    if (series.length === 0) {
      paintWaiting();
      return;
    }
    const request: ChartRenderRequest = {
      xLabel: "Частота, Гц",
      yLabel: saYAxisLabel(view.unit),
      x: Array.from(freq),
      xLog: view.xLog,
      xRange: view.xLog ? undefined : [freq[0] ?? 0, freq[freq.length - 1] ?? 0],
      series,
    };
    chart.render(request);
  }

  return {
    root,
    applyStore(store, view) {
      lastStore = store;
      render(store, view);
    },
    rerender(view) {
      if (lastStore === null) return;
      render(lastStore, view);
    },
    showProblem() {
      paintRejected();
    },
    destroy() {
      chart.destroy();
    },
  };
}
