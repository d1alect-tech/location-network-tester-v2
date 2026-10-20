/** Живая развёртка (Todo 8): рендер кадров обоих каналов общим стеком
 * графиков — createUplotView + decimateMinMax (todo 41), второй стек не
 * заводится. Окно осей фиксировано настройками (scopeScale): сетка
 * стабильна между кадрами, меняется только В/дел/пробник. Данные кадра
 * готовит сплит-модуль scopeWaveData (задача 16: выравнивание/прореживание
 * вынесены ДО роста модуля — точка разбиения в коммите). Нечисловые
 * отсчёты отбрасываются по правилу выравнивания рядов (prepareAligned);
 * выход за окно сетки и пустой кадр — видимый статус, без исключений.
 * Задача 24 (GATE A 2026-10-18): программный ФНЧ полосы — фильтр кадра
 * ПЕРЕД отрисовкой (режим setBwFilter), измерения не трогаются (считаются
 * по нефильтрованному payload в scopeMeasureConfig); ярлык состояния
 * [data-wave-bw] несёт подпись «программный фильтр, не аналоговый предел».
 * Хэндл регистрируется по фигуре (WeakMap, прецедент scopeCursorSection):
 * полоса находит его без правок воркспейса — findScopeWaveformView.
 * Задача 22: оверлей послесвечения поверх uPlot-канваса (пассивный
 * канвас, НЕ второй стек) — режим setPersistMode, накопление отображения
 * по каналам CH1/CH2 (после ФНЧ/прореживания), dt — из emitted_at_s.
 * Задача 16: математ-трасса CH1−CH2 — третья СЕРИЯ этого же стека (режим
 * setMathMode), разность отображаемых рядов, ярлык [data-wave-math]
 * (размах + честность 8 бит); в аккумулятор послесвечения трасса НЕ
 * входит — пин задачи 16 серия, не послесвечение. */

import type { LiveFramePayload } from "../../api/types-live";
import { readChartTheme } from "../../components/charts/theme";
import { MARKER_A, MARKER_B } from "../../components/charts/types";
import type { ChartRenderRequest, ChartRenderSeries } from "../../components/charts/types";
import { createUplotView } from "../../components/charts/uplotView";
import { el } from "../../components/primitives/dom";
import { BW_FILTER_HINT, BW_MODE_TEXT, type BwFilterMode, filterLiveFrame } from "./scopeBwFilter";
import { mathDiffVolts, mathTagText, mathTraceSeries, mathVppV } from "./scopeMathTrace";
import type { PersistenceMode } from "./scopePersistence";
import { yAxisRange } from "./scopeScale";
import { vdivTagText } from "./scopeScale";
import type { ScopeDisplaySettings } from "./scopeScale";
import { type WaveData, buildWaveData } from "./scopeWaveData";
import { createPersistenceTag, mountWavePersistence } from "./scopeWavePersistence";
import "./scopeWaveform.css";

const SYNC_KEY = "lnt-scope-waveform";
const CH2_DASH: readonly [number, number] = [6, 4];

export interface ScopeWaveformOptions {
  /** Тестовый шов (паттерн spectralOverlay): фабрика хэндла графика. */
  createView?: typeof createUplotView;
  /** Узел управления развёрткой (scopeControls) над графиком. */
  controls?: Node;
}

export interface ScopeWaveformHandle {
  readonly root: HTMLElement;
  /** Фигура развёртки (.lnt-scope-figure) — хост drag курсорных линий. */
  readonly figure: HTMLElement;
  /** Режим программного ФНЧ отображения (задача 24): фильтрует кадр
   *  перед отрисовкой, ярлык честности виден при любом не-full режиме. */
  setBwFilter(mode: BwFilterMode): void;
  /** Режим послесвечения отображения (задача 22): off / ~0,5 с / ~2 с. */
  setPersistMode(mode: PersistenceMode): void;
  /** Режим математ-трассы CH1−CH2 (задача 16): третья серия стека. */
  setMathMode(on: boolean): void;
  applyFrame(frame: LiveFramePayload, settings: ScopeDisplaySettings): void;
  /** Перерисовать последний кадр с новыми настройками (смена В/дел…). */
  rerender(settings: ScopeDisplaySettings): void;
  destroy(): void;
}

/** Хэндл развёртки по фигуре (WeakMap): полоса берёт его без селекторного
 *  поиска по DOM воркспейса — прецедент findScopeCursorView. */
const viewsByFigure = new WeakMap<HTMLElement, ScopeWaveformHandle>();

export function findScopeWaveformView(figure: HTMLElement): ScopeWaveformHandle | undefined {
  return viewsByFigure.get(figure);
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
  const bwTag = el("p", {
    className: "t-compact lnt-scope-wave-tag",
    attrs: { "data-wave-bw": "full", hidden: "" },
  });
  // Директива владельца 2026-10-19: ярлык честности вертикали — экранные
  // В/дел против входа АЦП (усиление ≥2× или сетка шире входа).
  const vdivTag = el("p", {
    className: "t-compact lnt-scope-wave-tag",
    attrs: { "data-wave-vdiv": "", hidden: "" },
  });
  // Задача 22: оверлей послесвечения — канвас ПОСЛЕ корня графика в DOM
  // (красится поверх), pointer-events: none — курсор/drag не задет.
  const persistOverlay = mountWavePersistence(figure);
  const persistTag = createPersistenceTag();
  // Задача 16: ярлык математ-трассы — та же строка ярлыков (без блока).
  const mathTag = el("p", {
    className: "t-compact lnt-scope-wave-tag",
    attrs: { "data-wave-math": "off", hidden: "" },
  });
  // Ряд состояния: ярлыки режимов (задачи 16/22/24 + вертикаль) + статус кадра.
  const meta = el("div", { className: "lnt-scope-wave-meta" }, [
    mathTag,
    bwTag,
    vdivTag,
    persistTag.root,
    status,
  ]);
  const bodyChildren: Node[] = [];
  if (options.controls !== undefined) bodyChildren.push(options.controls);
  bodyChildren.push(figure, meta);
  const root = el("section", { className: "panel lnt-scope-section lnt-scope-wave" }, [
    el("div", { className: "panel-hd" }, [
      el("h3", { className: "panel-title", text: "Живая развёртка" }),
    ]),
    el("div", { className: "panel-bd" }, bodyChildren),
  ]);
  let lastFrame: LiveFramePayload | null = null;
  let lastSettings: ScopeDisplaySettings | null = null;
  let lastEmitS: number | null = null;
  let bwMode: BwFilterMode = "full";
  let mathOn = false;

  function applyBwMode(mode: BwFilterMode): void {
    bwMode = mode;
    bwTag.setAttribute("data-wave-bw", mode);
    bwTag.hidden = mode === "full";
    bwTag.textContent = mode === "full" ? "" : `Полоса: ${BW_MODE_TEXT[mode]} — ${BW_FILTER_HINT}`;
  }

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

  function render(frame: LiveFramePayload, settings: ScopeDisplaySettings): WaveData | null {
    // Задача 24: ФНЧ отображения — вход рендера фильтрован, payload цел.
    const displayFrame = bwMode === "full" ? frame : filterLiveFrame(frame, bwMode);
    const data = buildWaveData(displayFrame, settings);
    announceProblems(data);
    if (data === null) return null; // предыдущий рендер остаётся, статус виден
    const theme = readChartTheme();
    const series: ChartRenderSeries[] = [
      { label: "CH1", values: data.ch1, color: theme.accentA, marker: MARKER_A },
      { label: "CH2", values: data.ch2, color: theme.accentB, dash: CH2_DASH, marker: MARKER_B },
    ];
    // Задача 16: разность ОТОБРАЖАЕМЫХ рядов — третья серия стека; нулевые
    // линии каналов НЕ входят в разность (математика без ground-сдвига).
    if (mathOn) {
      const raw1 = data.ch1.map((value) => value - settings.groundCh1V);
      const raw2 = data.ch2.map((value) => value - settings.groundCh2V);
      const diff = mathDiffVolts(raw1, raw2);
      series.push(mathTraceSeries(diff, theme));
      mathTag.textContent = mathTagText(mathVppV(diff));
    }
    const request: ChartRenderRequest = {
      xLabel: "Время, с",
      yLabel: "Напряжение, В",
      x: data.x,
      xRange: [data.xMin, data.xMax],
      yRange: yAxisRange(settings.vDiv, settings.probe),
      series,
    };
    const tag = vdivTagText(settings.vDiv, settings.probe);
    vdivTag.textContent = tag ?? "";
    vdivTag.hidden = tag === null;
    chart.render(request);
    return data;
  }

  const handle: ScopeWaveformHandle = {
    root,
    figure,
    setBwFilter(mode: BwFilterMode): void {
      if (bwMode === mode) return;
      applyBwMode(mode);
      // Смена режима перерисовывает последний кадр (тумблер горячий).
      if (lastFrame !== null && lastSettings !== null) render(lastFrame, lastSettings);
    },
    setPersistMode(mode: PersistenceMode): void {
      persistOverlay.setMode(mode);
      persistTag.paint(mode);
    },
    setMathMode(on: boolean): void {
      if (mathOn === on) return;
      mathOn = on;
      mathTag.setAttribute("data-wave-math", on ? "on" : "off");
      mathTag.hidden = !on;
      mathTag.textContent = on ? mathTagText(null) : "";
      // Тумблер горячий: последний кадр перерисовывается сразу.
      if (lastFrame !== null && lastSettings !== null) render(lastFrame, lastSettings);
    },
    applyFrame(frame, settings) {
      lastFrame = frame;
      lastSettings = settings;
      const data = render(frame, settings);
      if (data === null) return;
      // Задача 22: шаг накопления — затухание по dt кадра, оба канала.
      const emitS = frame.emitted_at_s;
      const dt =
        Number.isFinite(emitS) && lastEmitS !== null && emitS > lastEmitS
          ? emitS - lastEmitS
          : 1 / 30;
      if (Number.isFinite(emitS)) lastEmitS = emitS;
      const [yMin, yMax] = yAxisRange(settings.vDiv, settings.probe);
      persistOverlay.accumulate(data.x, data.ch1, data.ch2, yMin, yMax, dt);
    },
    rerender(settings) {
      lastSettings = settings;
      persistOverlay.clear();
      if (lastFrame === null) return;
      render(lastFrame, settings);
    },
    destroy() {
      persistOverlay.destroy();
      chart.destroy();
    },
  };
  viewsByFigure.set(figure, handle);
  return handle;
}
