/** Live-renderer спектрограммы захвата: адаптация frozen spectrogramV6.
 * Вместо attach(plot) — setFreqDomain(minHz, maxHz); данные — из LiveGramStore
 * через pushSpectrumColumn(freqHz, psdDb); кадры — из spectrogramLivePaint.
 * Палитра, токены, селекторы и readout-формат витрины сохранены. */

import { el } from "../components/primitives/dom";
import { clamp01 } from "../showcase-round2/spectrogramPalette";
import { gramScaleText, paintGramFrame } from "./spectrogramLivePaint";
import { FREQ_BINS, type LiveGramMode, LiveGramStore } from "./spectrogramLiveStore";

export { FREQ_BINS, TIME_BINS, LIVE_FLOOR_DB } from "./spectrogramLiveStore";
export type { LiveGramMode } from "./spectrogramLiveStore";

const FREQ_TICKS = [1000, 10000, 100000, 1000000, 10000000] as const;

const MODE_TITLE: Readonly<Record<LiveGramMode, string>> = {
  a: "База",
  b: "Сравнение",
  delta: "Δ live−фон",
};

/** Частота в русской нотации витрины: 22418 Гц -> «22 418 Гц». */
export function formatHzRu(value: number): string {
  return `${new Intl.NumberFormat("ru-RU").format(Math.round(value))} Гц`;
}

export interface SpectrogramLiveRenderer {
  readonly host: HTMLElement;
  readonly bar: HTMLElement;
  pushSpectrumColumn(frequencyHz: readonly number[], psdDb: readonly number[]): void;
  setFreqDomain(minHz: number, maxHz: number): void;
  freqDomain(): { minHz: number; maxHz: number };
  setMode(mode: LiveGramMode): void;
  getMode(): LiveGramMode;
  columnCount(): number;
  redraw(): void;
  dispose(): void;
}

export function buildSpectrogramLiveRenderer(secondsPerColumn = 1.5): SpectrogramLiveRenderer {
  const store = new LiveGramStore();
  let mode: LiveGramMode = "b";
  let disposed = false;
  let scheduled: number | null = null;
  let observer: ResizeObserver | null = null;

  const canvas = el("canvas", {
    className: "gram-canvas",
    attrs: { "data-spectrogram-canvas": "" },
  }) as HTMLCanvasElement;
  const readout = el("span", {
    className: "gram-readout num",
    attrs: { "data-spectrogram-readout": "" },
  });
  const scale = el("span", {
    className: "gram-scale",
    attrs: { "data-spectrogram-scale": "" },
  });
  const ticksRow = el("div", {
    className: "gram-freq-ticks",
    attrs: { "data-gram-freq-ticks": "", "aria-hidden": "true" },
  });

  // Позиции тиков — правилом стиль-листа, разметка свободна от inline-стилей.
  let sheet: CSSStyleSheet | null = null;
  try {
    if (typeof CSSStyleSheet === "function" && Array.isArray(document.adoptedStyleSheets)) {
      sheet = new CSSStyleSheet();
      document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
    }
  } catch {
    sheet = null;
  }

  const axisTicks: HTMLElement[] = [];
  const axis = el("div", { className: "gram-axis", attrs: { "aria-hidden": "true" } });
  for (let i = 0; i < 3; i += 1) {
    const tick = el("span", { className: "gram-tick num", text: "0 с" });
    axisTicks.push(tick);
    axis.append(tick);
  }

  function paintAxis(): void {
    const total = store.columnCount() * secondsPerColumn;
    const labels = ["0 с", `${(total / 2).toFixed(1)} с`, `${total.toFixed(1)} с`];
    axisTicks.forEach((node, i) => {
      node.textContent = labels[i] as string;
    });
  }

  function paintFrame(): void {
    if (disposed) return;
    paintGramFrame(canvas, store, mode);
    scale.textContent = gramScaleText(mode, store.levelRange());
    paintAxis();
  }

  function markDirty(): void {
    if (disposed || scheduled !== null) return;
    if (typeof globalThis.requestAnimationFrame === "function") {
      scheduled = globalThis.requestAnimationFrame.call(globalThis, () => {
        scheduled = null;
        paintFrame();
      });
    } else {
      scheduled = setTimeout(() => {
        scheduled = null;
        paintFrame();
      }, 16) as unknown as number;
    }
  }

  function paintTicks(): void {
    while (ticksRow.firstChild) ticksRow.removeChild(ticksRow.firstChild);
    for (const hz of FREQ_TICKS) {
      ticksRow.append(
        el("span", {
          className: "gram-freq-tick num",
          attrs: { "data-hz": String(hz) },
          text: hz.toLocaleString("en-US"),
        }),
      );
    }
    if (sheet === null) return;
    const { minHz, maxHz } = store.freqDomain();
    const span = Math.log10(maxHz) - Math.log10(minHz);
    try {
      sheet.replaceSync(
        FREQ_TICKS.map((hz) => {
          const t = ((Math.log10(hz) - Math.log10(minHz)) / span) * 100;
          return `.app-v6 [data-hz="${hz}"], .capture-view [data-hz="${hz}"]{left:${t.toFixed(2)}%}`;
        }).join(""),
      );
    } catch {
      // Конструктивные таблицы стилей недоступны — тики остаются подписанными.
    }
  }

  function freqAt(cssX: number, cssWidth: number): number {
    const { minHz, maxHz } = store.freqDomain();
    if (!(cssWidth > 0)) return minHz;
    const logMin = Math.log10(minHz);
    return 10 ** (logMin + clamp01(cssX / cssWidth) * (Math.log10(maxHz) - logMin));
  }

  const modes = el("div", {
    className: "gram-modes",
    attrs: { role: "group", "aria-label": "Содержимое спектрограммы" },
  });
  const buttons = new Map<LiveGramMode, HTMLElement>();
  for (const key of ["a", "b", "delta"] as const) {
    const button = el("button", {
      className: "btn-quiet gram-mode",
      attrs: {
        type: "button",
        "data-spectrogram-mode": key,
        "aria-pressed": String(key === mode),
      },
      text: MODE_TITLE[key],
    });
    button.addEventListener("click", () => {
      mode = key;
      for (const [name, node] of buttons) node.setAttribute("aria-pressed", String(name === key));
      markDirty();
    });
    buttons.set(key, button);
    modes.append(button);
  }

  canvas.addEventListener("mousemove", (event) => {
    const mouse = event as MouseEvent;
    const box = canvas.getBoundingClientRect();
    const x = mouse.clientX - box.left;
    const timeNorm = box.height > 0 ? clamp01((mouse.clientY - box.top) / box.height) : 0;
    const freq = freqAt(x, box.width);
    const bin = Math.min(FREQ_BINS - 1, Math.floor(clamp01(x / (box.width || 1)) * FREQ_BINS));
    const count = store.columnCount();
    const k = count === 0 ? 0 : Math.min(count - 1, Math.floor(timeNorm * count));
    const row = count === 0 ? 0 : store.rowPhysical(k);
    const value = store.valueAt(bin, row, mode);
    const seconds = (k * secondsPerColumn).toFixed(2);
    const sign = mode === "delta" && value > 0 ? "+" : "";
    readout.textContent = `${formatHzRu(freq)} · ${seconds} с · ${sign}${value.toFixed(1)} дБ`;
  });
  canvas.addEventListener("mouseleave", () => {
    readout.textContent = "наведите на полотно";
  });

  const bar = el("div", { className: "gram-bar" }, [modes, readout, scale]);
  const wrap = el("div", { className: "gram-canvas-wrap" }, [axis, canvas]);
  const host = el("div", { className: "gram", attrs: { "data-spectrogram": "" } }, [
    wrap,
    ticksRow,
  ]);

  try {
    if (typeof ResizeObserver === "function") {
      observer = new ResizeObserver(() => paintFrame());
      observer.observe(wrap);
    }
  } catch {
    observer = null;
  }

  paintTicks();
  return {
    host,
    bar,
    pushSpectrumColumn(frequencyHz, psdDb) {
      if (disposed) return;
      if (store.pushSpectrumColumn(frequencyHz, psdDb)) markDirty();
    },
    setFreqDomain(minHz, maxHz) {
      if (!store.setFreqDomain(minHz, maxHz)) return;
      paintTicks();
      markDirty();
    },
    freqDomain() {
      return store.freqDomain();
    },
    setMode(next) {
      mode = next;
      for (const [name, node] of buttons) node.setAttribute("aria-pressed", String(name === next));
      markDirty();
    },
    getMode() {
      return mode;
    },
    columnCount() {
      return store.columnCount();
    },
    redraw() {
      markDirty();
    },
    dispose() {
      disposed = true;
      if (scheduled !== null) {
        if (typeof globalThis.cancelAnimationFrame === "function") {
          globalThis.cancelAnimationFrame.call(globalThis, scheduled);
        } else clearTimeout(scheduled);
        scheduled = null;
      }
      observer?.disconnect();
      observer = null;
      if (sheet !== null) {
        try {
          if (Array.isArray(document.adoptedStyleSheets)) {
            document.adoptedStyleSheets = document.adoptedStyleSheets.filter((s) => s !== sheet);
          }
        } catch {
          // Снятие таблицы стилей необязательно для teardown.
        }
        sheet = null;
      }
    },
  };
}
