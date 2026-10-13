/** Живая развёртка (Todo 8): рендер кадров обоих каналов общим стеком
 * графиков — createUplotView + decimateMinMax (todo 41), второй стек не
 * заводится. Окно осей фиксировано настройками (scopeScale): сетка
 * стабильна между кадрами, меняется только В/дел/пробник. Данные кадра
 * копируются (инверсия — знак копии, исходники не мутируются). Нечисловые
 * отсчёты отбрасываются по правилу выравнивания рядов (prepareAligned);
 * выход за окно сетки и пустой кадр — видимый статус, без исключений. */

import type { LiveFramePayload } from "../../api/types-live";
import { decimateMinMax } from "../../components/charts/series";
import { readChartTheme } from "../../components/charts/theme";
import { MARKER_A, MARKER_B } from "../../components/charts/types";
import type { ChartRenderRequest } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import { POINT_BUDGETS } from "../../components/charts/viewModels";
import { el } from "../../components/primitives/dom";
import { halfSpanVolts, yAxisRange } from "./scopeScale";
import type { ScopeDisplaySettings } from "./scopeScale";
import "./scopeWaveform.css";

const SYNC_KEY = "lnt-scope-waveform";
const WAVE_BUDGET = POINT_BUDGETS.waveform.default;
const CH2_DASH: readonly [number, number] = [6, 4];

export interface ScopeWaveformOptions {
  /** Тестовый шов (паттерн spectralOverlay): фабрика хэндла графика. */
  createView?: typeof createUplotView;
  /** Узел управления развёрткой (scopeControls) над графиком. */
  controls?: Node;
}

export interface ScopeWaveformHandle {
  readonly root: HTMLElement;
  applyFrame(frame: LiveFramePayload, settings: ScopeDisplaySettings): void;
  /** Перерисовать последний кадр с новыми настройками (смена В/дел…). */
  rerender(settings: ScopeDisplaySettings): void;
  destroy(): void;
}

interface WaveData {
  x: number[];
  ch1: number[];
  ch2: number[];
  xMin: number;
  xMax: number;
  nanCount: number;
  clipCount: number;
}

/** Общее прореживание пары каналов: min/max-огибающая каждого канала
 * (decimateMinMax), объединение сохранённых индексов — экстремумы обоих
 * каналов остаются, ряды выровнены по общему X. */
function decimateUnion(data: WaveData): void {
  if (data.x.length <= WAVE_BUDGET) return;
  const indexByX = new Map<number, number>();
  for (let i = 0; i < data.x.length; i += 1) indexByX.set(data.x[i]!, i);
  const kept = new Set<number>();
  for (const channel of [data.ch1, data.ch2]) {
    for (const xValue of decimateMinMax(data.x, channel, WAVE_BUDGET).x) {
      const index = indexByX.get(xValue);
      if (index !== undefined) kept.add(index);
    }
  }
  const indices = [...kept].sort((a, b) => a - b);
  data.x = indices.map((index) => data.x[index]!);
  data.ch1 = indices.map((index) => data.ch1[index]!);
  data.ch2 = indices.map((index) => data.ch2[index]!);
}

/** Кадр -> выровненные копии рядов: знак инверсии, отбрасывание нечисловых
 * по общему индексу (как prepareAligned), подсчёт выхода за окно сетки. */
function buildWaveData(frame: LiveFramePayload, settings: ScopeDisplaySettings): WaveData | null {
  const times = frame.ch1.time_s;
  const rawCh1 = frame.ch1.voltage_v;
  const rawCh2 = frame.ch2.voltage_v;
  const count = Math.min(times.length, rawCh1.length, rawCh2.length);
  if (count === 0) return null;
  const half = halfSpanVolts(settings.vDiv, settings.probe);
  const signCh1 = settings.invertCh1 ? -1 : 1;
  const signCh2 = settings.invertCh2 ? -1 : 1;
  const data: WaveData = {
    x: [],
    ch1: [],
    ch2: [],
    xMin: Number.POSITIVE_INFINITY,
    xMax: Number.NEGATIVE_INFINITY,
    nanCount: 0,
    clipCount: 0,
  };
  for (let i = 0; i < count; i += 1) {
    const t = times[i];
    const v1 = rawCh1[i];
    const v2 = rawCh2[i];
    if (t === undefined || v1 === undefined || v2 === undefined) {
      data.nanCount += 1;
      continue;
    }
    if (!Number.isFinite(t) || !Number.isFinite(v1) || !Number.isFinite(v2)) {
      data.nanCount += 1;
      continue;
    }
    const w1 = v1 * signCh1;
    const w2 = v2 * signCh2;
    if (Math.abs(w1) > half || Math.abs(w2) > half) data.clipCount += 1;
    data.x.push(t);
    data.ch1.push(w1);
    data.ch2.push(w2);
    if (t < data.xMin) data.xMin = t;
    if (t > data.xMax) data.xMax = t;
  }
  if (data.x.length === 0) return null;
  decimateUnion(data);
  return data;
}

export function mountScopeWaveform(options: ScopeWaveformOptions = {}): ScopeWaveformHandle {
  const factory = options.createView ?? createUplotView;
  const figure = el("div", { className: "lnt-scope-figure" });
  const status = el("p", {
    className: "lnt-scope-wave-status",
    text: "ожидание кадра…",
    attrs: { role: "status", "data-wave-state": "waiting" },
  });
  const chart = factory({ container: figure, syncKey: SYNC_KEY });
  // Корень хэндла монтируется в фигуру (как ChartShell.setContent): его
  // CSS-высота даёт контейнеру размер, иначе draw() уходит по нулю.
  figure.append(chart.root);
  const bodyChildren: Node[] = [];
  if (options.controls !== undefined) bodyChildren.push(options.controls);
  bodyChildren.push(figure, status);
  const root = el("section", { className: "panel lnt-scope-section lnt-scope-wave" }, [
    el("div", { className: "panel-hd" }, [
      el("h3", { className: "panel-title", text: "Живая развёртка" }),
    ]),
    el("div", { className: "panel-bd" }, bodyChildren),
  ]);
  let lastFrame: LiveFramePayload | null = null;

  function announceProblems(data: WaveData | null): void {
    if (data === null) {
      status.hidden = false;
      status.setAttribute("data-wave-state", "empty");
      status.textContent = "кадр без точек";
      return;
    }
    const problems: string[] = [];
    if (data.clipCount > 0) {
      problems.push(`отсчётов вне сетки: ${data.clipCount} — увеличьте В/дел`);
    }
    if (data.nanCount > 0) problems.push(`нечисловых отсчётов отброшено: ${data.nanCount}`);
    if (problems.length === 0) {
      status.hidden = true;
      status.setAttribute("data-wave-state", "ok");
      status.textContent = "";
      return;
    }
    status.hidden = false;
    status.setAttribute("data-wave-state", "problem");
    status.textContent = problems.join("; ");
  }

  function render(frame: LiveFramePayload, settings: ScopeDisplaySettings): void {
    const data = buildWaveData(frame, settings);
    announceProblems(data);
    if (data === null) return; // предыдущий рендер остаётся, статус виден
    const theme = readChartTheme();
    const request: ChartRenderRequest = {
      xLabel: "Время, с",
      yLabel: "Напряжение, В",
      x: data.x,
      xRange: [data.xMin, data.xMax],
      yRange: yAxisRange(settings.vDiv, settings.probe),
      series: [
        { label: "CH1", values: data.ch1, color: theme.accentA, marker: MARKER_A },
        { label: "CH2", values: data.ch2, color: theme.accentB, dash: CH2_DASH, marker: MARKER_B },
      ],
    };
    chart.render(request);
  }

  return {
    root,
    applyFrame(frame, settings) {
      lastFrame = frame;
      render(frame, settings);
    },
    rerender(settings) {
      if (lastFrame === null) return;
      render(lastFrame, settings);
    },
    destroy() {
      chart.destroy();
    },
  };
}
