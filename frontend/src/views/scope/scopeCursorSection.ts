/** Курсоры осциллографа (Todo 10): ползунки T1/T2 (доли окна кадра) и
 * V1/V2 (вольты номинальной шкалы ±5 В) + readout Δt/ΔV. Линии рисует
 * uPlot-плагин (паттерн annotations.createPeaksPlugin: valToPos + bbox,
 * стиль из токенов) — плагин пробрасывается в стек развёртки через шов
 * createView в scopeWorkspace и живёт в каждой пересборке uPlot. Плагин
 * же сообщает окно X графика в readout (зум виден честно); без графика
 * (jsdom/нет кадра) окно берётся из кадра, Δt — «—». Математика — чистые
 * scopeCursors/scopeMeasurements, DOM не выше этого модуля. */

import type uPlot from "uplot";
import type { LiveChannelSeries, LiveFramePayload } from "../../api/types-live";
import { el } from "../../components/primitives/dom";
import {
  VOLT_CURSOR_SPAN_V,
  clampFraction,
  formatDeltaSecondsValue,
  formatDeltaVoltsValue,
  timeCursorDeltaSeconds,
  voltageCursorDeltaV,
} from "./scopeCursors";
import { formatPeriodValue, formatVoltsValue } from "./scopeMeasurements";

export interface ScopeCursorView {
  /** Панель «Курсоры»: ползунки + readout Δt/ΔV. */
  readonly root: HTMLElement;
  /** Плагин линий курсоров для стека развёртки (шов createView). */
  readonly plugin: uPlot.Plugin;
  /** Кадр задаёт окно времени T-курсоров, пока график не сообщил своё. */
  applyFrame(frame: LiveFramePayload): void;
}

interface CursorPositions {
  t1: number;
  t2: number;
  v1: number;
  v2: number;
}

interface CursorTheme {
  readonly timeCursor: string;
  readonly voltCursor: string;
  readonly label: string;
}

/** Резервы — значения v2-tokens.css; в браузере читаются актуальные
 * токены (jsdom не каскадирует custom properties), паттерн charts/theme. */
const FALLBACK: CursorTheme = {
  timeCursor: "#b7a6ff",
  voltCursor: "#3dbd8a",
  label: "#aeb6bf",
};

const DEFAULT_T1 = 0.25;
const DEFAULT_T2 = 0.75;
const DEFAULT_V1 = -1;
const DEFAULT_V2 = 1;

/** Поле курсора: подпись + ползунок; возвращает обёртку и input. */
function cursorField(
  id: string,
  label: string,
  min: number,
  max: number,
  value: number,
  sliderClass: string,
): { field: HTMLElement; input: HTMLInputElement } {
  const input = el("input", {
    className: `lnt-scope-cursor-slider ${sliderClass}`,
    attrs: {
      type: "range",
      id,
      min: String(min),
      max: String(max),
      step: "5",
      value: String(value),
      "aria-label": label,
    },
  });
  const caption = el("label", { className: "lnt-scope-cursor-label", text: label });
  caption.htmlFor = id;
  return {
    input,
    field: el("div", { className: "lnt-scope-cursor-field" }, [caption, input]),
  };
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

  function updateCursorReadout(): void {
    if (windowS === null) {
      t1Value.textContent = "—";
      t2Value.textContent = "—";
    } else {
      t1Value.textContent = formatPeriodValue(t0 + positions.t1 * windowS);
      t2Value.textContent = formatPeriodValue(t0 + positions.t2 * windowS);
    }
    dtValue.textContent = formatDeltaSecondsValue(
      timeCursorDeltaSeconds({ t1: positions.t1, t2: positions.t2 }, windowS),
    );
    v1Value.textContent = formatVoltsValue(positions.v1);
    v2Value.textContent = formatVoltsValue(positions.v2);
    dvValue.textContent = formatDeltaVoltsValue(
      voltageCursorDeltaV({ v1: positions.v1, v2: positions.v2 }),
    );
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
        drawCursorLines(self, () => positions);
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

  return {
    root: el("section", { className: "panel lnt-scope-section lnt-scope-cursors" }, [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "panel-title", text: "Курсоры" }),
      ]),
      el("div", { className: "panel-bd" }, [
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
  };
}

/** Линии курсоров в координатах uPlot (паттерн createPeaksPlugin):
 * T — вертикали на доле окна X, V — горизонтали по вольтам оси Y. */
function drawCursorLines(self: uPlot, readPositions: () => CursorPositions): void {
  const ctx = self.ctx;
  if (ctx === null) return;
  const positions = readPositions();
  const bbox = self.bbox;
  const theme = cursorTheme(self.root);
  ctx.save();
  ctx.lineWidth = 1;
  ctx.font = '600 10px "IBM Plex Mono", monospace';

  const xMin = self.scales.x?.min;
  const xMax = self.scales.x?.max;
  const timePairs: ReadonlyArray<readonly [string, number]> = [
    ["T1", positions.t1],
    ["T2", positions.t2],
  ];
  for (const [label, fraction] of timePairs) {
    if (typeof xMin !== "number" || typeof xMax !== "number") continue;
    const xValue = xMin + clampFraction(fraction) * (xMax - xMin);
    const x = self.valToPos(xValue, "x");
    ctx.strokeStyle = theme.timeCursor;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x, bbox.top);
    ctx.lineTo(x, bbox.top + bbox.height);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = theme.label;
    ctx.fillText(label, Math.min(x + 3, bbox.left + bbox.width - 16), bbox.top + 24);
  }

  const voltPairs: ReadonlyArray<readonly [string, number]> = [
    ["V1", positions.v1],
    ["V2", positions.v2],
  ];
  for (const [label, volts] of voltPairs) {
    const y = self.valToPos(volts, "y");
    ctx.strokeStyle = theme.voltCursor;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(bbox.left, y);
    ctx.lineTo(bbox.left + bbox.width, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = theme.label;
    ctx.fillText(label, bbox.left + 24, y < bbox.top + 24 ? y + 12 : y - 4);
  }
  ctx.restore();
}

function cursorTheme(root: HTMLElement): CursorTheme {
  const styles = getComputedStyle(root);
  const token = (name: string, fallback: string): string =>
    styles.getPropertyValue(name).trim() || fallback;
  return {
    timeCursor: token("--lnt-delta", FALLBACK.timeCursor),
    voltCursor: token("--lnt-ok", FALLBACK.voltCursor),
    label: token("--lnt-text-sec", FALLBACK.label),
  };
}

/** Окно времени канала: последний − первый отсчёт; пусто/вырождено — null. */
function timeWindowS(series: LiveChannelSeries): number | null {
  const first = series.time_s[0];
  const last = series.time_s[series.time_s.length - 1];
  if (first === undefined || last === undefined) return null;
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
  const span = last - first;
  return span > 0 ? span : null;
}
