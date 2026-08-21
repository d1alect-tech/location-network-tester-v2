/** Мост определений графиков на uPlot (todo 41): сохраняет контракт данных
 * панели {traces:[{x,y,...}], layout:{xaxis,yaxis}} из payload-функций бэкенда,
 * отрисовку выполняет локально вендоренный uPlot (без внешних запросов). */

import uPlot from "./vendor/uPlot.esm.js";

export const UPLOT_VERSION = "1.6.32";

/** «dash»/«dot» из определения линии → шаблон штрихов uPlot (нецветовая метка Б). */
export function dashPattern(dash) {
  if (dash === "dash" || dash === "dashed") return [6, 4];
  if (dash === "dot" || dash === "dotted") return [2, 3];
  return undefined;
}

/** Log-safe фильтрация пар для лог-осей (зеркало бэкендной decimate_spectrum):
 * детерминированно отбрасываются пары с нечисловыми значениями и значениями ≤ 0. */
export function logSafePairs(x, y) {
  const outX = [];
  const outY = [];
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i += 1) {
    const xi = x[i];
    const yi = y[i];
    if (Number.isFinite(xi) && Number.isFinite(yi) && xi > 0 && yi > 0) {
      outX.push(xi);
      outY.push(yi);
    }
  }
  return { x: outX, y: outY };
}

function seriesData(definition) {
  const trace = definition.traces[0];
  const xLog = definition.layout?.xaxis?.type === "log";
  const yLog = definition.layout?.yaxis?.type === "log";
  if (!xLog && !yLog) return [[...trace.x], [...trace.y]];
  const pairs = logSafePairs(trace.x, trace.y);
  return [pairs.x, pairs.y];
}

function axisOpts(axis, tokens) {
  return {
    label: axis.title,
    stroke: tokens.text,
    grid: { stroke: tokens.grid, width: tokens.lineWidth },
    ticks: { stroke: tokens.grid, width: tokens.lineWidth },
    font: `${12}px ${tokens.fontMono ?? "monospace"}`,
    labelFont: `${13}px ${tokens.fontSans ?? "sans-serif"}`,
  };
}

function buildOptions(definition, tokens, width, height) {
  const trace = definition.traces[0];
  const xaxis = definition.layout.xaxis ?? {};
  const yaxis = definition.layout.yaxis ?? {};
  const xLog = xaxis.type === "log";
  const yLog = yaxis.type === "log";
  const rangeFn = (_self, initMin, initMax) => uPlot.rangeLog(initMin, initMax, 10, true);
  return {
    width,
    height,
    class: "legacy-uplot",
    series: [
      {},
      {
        label: trace.name ?? "",
        stroke: trace.line?.color ?? tokens.lineA,
        width: trace.line?.width ?? tokens.lineWidth + 0.5,
        dash: dashPattern(trace.line?.dash),
        points: { show: false },
        spanGaps: true,
      },
    ],
    scales: {
      x: { time: false, ...(xLog ? { distr: 3, log: 10, range: rangeFn } : {}) },
      y: yLog ? { distr: 3, log: 10, range: rangeFn } : {},
    },
    axes: [axisOpts(xaxis, tokens), axisOpts(yaxis, tokens)],
    legend: { show: true, live: true },
    cursor: { drag: { setScale: true, x: true, y: false } },
  };
}

function mountSize(target) {
  const rect = target.getBoundingClientRect();
  return {
    width: Math.max(320, Math.floor(rect.width) || 640),
    height: Math.floor(rect.height) || Number.parseInt(getComputedStyle(target).height, 10) || 260,
  };
}

/** Мини-фасад совместимости: newPlot/react как у прежней библиотеки,
 * чтобы планировщик renderer'а и его тесты сохраняли контракт. */
export function createUplotChart({ documentRef }) {
  const instances = new Map();

  function render(target, traces, layout, mode) {
    const tokens = mode.tokens;
    const definition = { traces, layout };
    const data = seriesData(definition);
    const existing = instances.get(target);
    if (existing !== undefined && target.contains(existing.root)) {
      const { width, height } = mountSize(target);
      existing.setSize({ width, height });
      existing.setData(data);
      return;
    }
    target.replaceChildren();
    const host = documentRef.createElement("div");
    target.append(host);
    const { width, height } = mountSize(target);
    const options = buildOptions(definition, tokens, width, height);
    instances.set(target, new uPlot(options, data, host));
  }

  return {
    /** Отрисовка нового графика в целевом элементе. */
    newPlot(target, traces, layout, config) {
      render(target, traces, layout, config);
      return { mode: config.mode };
    },
    /** Перекраска существующего графика свежими токенами темы. */
    react(target, traces, layout, config) {
      render(target, traces, layout, config);
      return { mode: config.mode };
    },
  };
}
