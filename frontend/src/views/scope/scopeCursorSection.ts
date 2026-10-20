/** Курсоры осциллографа (Todo 10): ползунки T1/T2 (доли окна кадра) и
 * V1/V2 (вольты номинальной шкалы ±5 В) + readout Δt/ΔV. Тумблер
 * Выкл|Вкл и поиск хэндла (findScopeCursorView, chart) — задача 15:
 * полоса и drag линий берут состояние/геометрию без правок воркспейса. Линии рисует
 * uPlot-плагин (паттерн annotations.createPeaksPlugin: valToPos + bbox,
 * стиль из токенов) — плагин пробрасывается в стек развёртки через шов
 * createView в scopeWorkspace и живёт в каждой пересборке uPlot. Плагин
 * же сообщает окно X графика в readout (зум виден честно); без графика
 * (jsdom/нет кадра) окно берётся из кадра, Δt — «—». Модель — чистые
 * scopeCursorModel/scopeCursors/scopeMeasurements, линии — scopeCursorPaint;
 * DOM не выше этого модуля. */

import type uPlot from "uplot";
import type { LiveFramePayload } from "../../api/types-live";
import { createLiveSeg } from "../../components/liveStrip/liveSeg";
import { el } from "../../components/primitives/dom";
import { cursorField, setVoltageCursorWindow } from "./scopeCursorFields";
import {
  type CursorPositions,
  DEFAULT_T1,
  DEFAULT_T2,
  DEFAULT_V1,
  DEFAULT_V2,
  cursorReadout,
  timeWindowS,
} from "./scopeCursorModel";
import { drawCursorLines } from "./scopeCursorPaint";
import { VOLT_CURSOR_SPAN_V, clampFraction } from "./scopeCursors";

export interface ScopeCursorView {
  /** Панель «Курсоры»: тумблер линий + ползунки + readout Δt/ΔV. */
  readonly root: HTMLElement;
  /** Тумблер линий (#lnt-scope-cursors) — хост полосы (ре-парент). */
  readonly toggle: HTMLElement;
  /** Слайдеры T1/T2/V1/V2 — скрытый leftover с живыми слушателями. */
  readonly sliders: {
    readonly t1: HTMLInputElement;
    readonly t2: HTMLInputElement;
    readonly v1: HTMLInputElement;
    readonly v2: HTMLInputElement;
  };
  /** Инлайн-ридаут «Δt … · ΔV …» (r4-грамматика): полоса liveStrip несёт
   * одну строку без обрезки — клетки сетки не сжимаются (задача r5-9 W3). */
  readonly inlineReadout: HTMLElement;
  /** Плагин линий курсоров для стека развёртки (шов createView). */
  readonly plugin: uPlot.Plugin;
  /** Кадр задаёт окно времени T-курсоров, пока график не сообщил своё. */
  applyFrame(frame: LiveFramePayload): void;
  /** Тумблер Выкл|Вкл: линии гаснут, позиционирование живо (задача 15). */
  cursorsOn(): boolean;
  /** Текущий инстанс uPlot — геометрия для drag линий (scopeCursorDrag). */
  chart(): uPlot | null;
  setWindow(half: number): void;
}

/** Хэндлы секций по корню: полоса берёт геометрию/состояние без правок
 * воркспейса (WeakMap — ключ живёт, пока жив DOM секции). */
const viewsByRoot = new WeakMap<HTMLElement, ScopeCursorView>();

export function findScopeCursorView(root: HTMLElement): ScopeCursorView | undefined {
  return viewsByRoot.get(root);
}

export function buildScopeCursorSection(): ScopeCursorView {
  const t1 = cursorField("lnt-scope-cursor-t1", "Курсор T1", 0, 1000, 250, "lnt-scope-slider-t");
  const t2 = cursorField("lnt-scope-cursor-t2", "Курсор T2", 0, 1000, 750, "lnt-scope-slider-t");
  const v1 = cursorField(
    "lnt-scope-cursor-v1",
    "Курсор V1",
    -VOLT_CURSOR_SPAN_V * 100,
    VOLT_CURSOR_SPAN_V * 100,
    DEFAULT_V1 * 100,
    "lnt-scope-slider-v",
  );
  const v2 = cursorField(
    "lnt-scope-cursor-v2",
    "Курсор V2",
    -VOLT_CURSOR_SPAN_V * 100,
    VOLT_CURSOR_SPAN_V * 100,
    DEFAULT_V2 * 100,
    "lnt-scope-slider-v",
  );

  const t1Value = el("dd", { className: "t-mono lnt-scope-cursor-t1", text: "—" });
  const t2Value = el("dd", { className: "t-mono lnt-scope-cursor-t2", text: "—" });
  const dtValue = el("dd", { className: "t-mono lnt-scope-cursor-dt", text: "—" });
  const v1Value = el("dd", { className: "t-mono lnt-scope-cursor-v1", text: "—" });
  const v2Value = el("dd", { className: "t-mono lnt-scope-cursor-v2", text: "—" });
  const dvValue = el("dd", { className: "t-mono lnt-scope-cursor-dv", text: "—" });
  const inlineReadout = el("span", {
    className: "t-mono lnt-scope-cursor-inline",
    text: "Δt — · ΔV —",
    attrs: { "data-readonly": "" },
  });
  const row = (label: string, value: HTMLElement): Node[] => [
    el("dt", { className: "readout-label", text: label }),
    value,
  ];

  const positions: CursorPositions = {
    t1: DEFAULT_T1,
    t2: DEFAULT_T2,
    v1: DEFAULT_V1,
    v2: DEFAULT_V2,
  };
  let windowS: number | null = null;
  let t0 = 0;
  /** Текущий инстанс uPlot (пересоздаётся на каждом кадре) для redraw. */
  let chart: uPlot | null = null;
  /** Тумблер Выкл|Вкл: линии гаснут, позиции и readout живут (задача 15). */
  let enabled = true;

  const toggle = createLiveSeg(
    {
      key: "cursors",
      kind: "local",
      aria: "Линии курсоров",
      options: [
        { value: "off", text: "Выкл" },
        { value: "on", text: "Вкл" },
      ],
      current: "on",
      groupAttrs: { id: "lnt-scope-cursors" },
    },
    (value) => {
      enabled = value === "on";
      chart?.redraw();
    },
  );

  function updateCursorReadout(): void {
    const readout = cursorReadout(positions, windowS, t0);
    t1Value.textContent = readout.t1;
    t2Value.textContent = readout.t2;
    dtValue.textContent = readout.dt;
    v1Value.textContent = readout.v1;
    v2Value.textContent = readout.v2;
    dvValue.textContent = readout.dv;
    inlineReadout.textContent = `Δt ${readout.dt} · ΔV ${readout.dv}`;
  }

  for (const [control, apply] of [
    [
      t1.input,
      (raw: number) => {
        positions.t1 = clampFraction(raw / 1000);
      },
    ],
    [
      t2.input,
      (raw: number) => {
        positions.t2 = clampFraction(raw / 1000);
      },
    ],
    [
      v1.input,
      (raw: number) => {
        positions.v1 = raw / 100;
      },
    ],
    [
      v2.input,
      (raw: number) => {
        positions.v2 = raw / 100;
      },
    ],
  ] as const) {
    control.addEventListener("input", () => {
      apply(Number(control.value));
      updateCursorReadout();
      chart?.redraw();
    });
  }

  const plugin: uPlot.Plugin = {
    hooks: {
      init: (self: uPlot) => {
        chart = self;
      },
      draw: (self: uPlot) => {
        if (enabled) drawCursorLines(self, () => positions);
        // Окно X графика — истина для T-курсоров (зум честно попадает в Δt).
        const xScale = self.scales.x;
        const min = xScale?.min;
        const max = xScale?.max;
        if (typeof min === "number" && typeof max === "number" && max > min) {
          t0 = min;
          windowS = max - min;
          updateCursorReadout();
        }
      },
    },
  };

  // Курсоры напряжения живут в номинальной шкале — readout виден и до
  // первого кадра; T-строки остаются «—» до окна кадра.
  updateCursorReadout();

  const view: ScopeCursorView = {
    inlineReadout,
    toggle: toggle.root,
    sliders: { t1: t1.input, t2: t2.input, v1: v1.input, v2: v2.input },
    root: el("section", { className: "panel lnt-scope-section lnt-scope-cursors" }, [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "panel-title", text: "Курсоры" }),
      ]),
      el("div", { className: "panel-bd" }, [
        toggle.root,
        el("p", { className: "t-compact lnt-scope-legend" }, [
          el("span", { className: "lnt-scope-legend-item" }, [
            el("span", { className: "lnt-scope-legend-dot lnt-scope-dot-t" }),
            el("span", { text: "курсоры T" }),
          ]),
          el("span", { className: "lnt-scope-legend-item" }, [
            el("span", { className: "lnt-scope-legend-dot lnt-scope-dot-v" }),
            el("span", { text: "курсоры V" }),
          ]),
        ]),
        el("div", { className: "lnt-scope-cursor-controls" }, [
          t1.field,
          t2.field,
          v1.field,
          v2.field,
        ]),
        el(
          "dl",
          { className: "readout-grid" },
          row("T1", t1Value)
            .concat(row("T2", t2Value))
            .concat(row("Δt", dtValue))
            .concat(row("V1", v1Value))
            .concat(row("V2", v2Value))
            .concat(row("ΔV", dvValue)),
        ),
        inlineReadout,
        el("p", {
          className: "t-compact",
          text: "Курсоры T — доли окна кадра, V — номинальная шкала ±5 В.",
        }),
      ]),
    ]),
    plugin,
    applyFrame(frame: LiveFramePayload): void {
      if (chart !== null) return; // окно сообщает плагин из осей графика
      const span = timeWindowS(frame.ch1);
      windowS = span;
      t0 = span === null ? 0 : (frame.ch1.time_s[0] ?? 0);
      updateCursorReadout();
    },
    cursorsOn: () => enabled,
    chart: () => chart,
    setWindow(half): void {
      setVoltageCursorWindow(v1.input, v2.input, positions, half);
      updateCursorReadout();
    },
  };
  viewsByRoot.set(view.root, view);
  return view;
}
