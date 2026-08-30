/** Спектрограмма V6 — отдельный вид сигнального окна: время × частота.
 *
 *  Спектр и спектрограмма не стоят стопкой: это два переключаемых вида одного
 *  окна. Шкала частот у грама собственная, но значения и лог-позиции она берёт
 *  у шкалы спектра при attach, поэтому оба вида говорят на одной шкале.
 *  Ось X — частота, ось Y — время записи.
 *
 *  Содержимое переключается А / Б / Δ: по умолчанию уровень сравнения —
 *  спокойная дельта вдали от пиков почти чёрная и читалась бы пустым полем. */
import type uPlot from "uplot";

import { METRICS, formatHz } from "../showcase-redesign/data";
import { buildSpectrumData } from "../showcase-redesign/spectrum";
import { h } from "./kit";
import { DELTA_SPAN_DB, clamp01, deltaColor, heatColor } from "./spectrogramPalette";

type Mode = "a" | "b" | "delta";

// 48 бинов и 4 периода: на полном наборе бинов сумма косинусов точно нулевая.
const TIME_BINS = 48;
const TIME_PERIODS = 4;
const DAMPED_HZ = 22418;
const FREQ_TICKS = [1000, 10000, 100000, 1000000, 10000000] as const;

const MODE_TITLE: Readonly<Record<Mode, string>> = {
  a: "База",
  b: "Сравнение",
  delta: "Δ Б−А",
};

/** Колонка uPlot: обычный или типизированный массив, возможно с дырами. */
type Column = { readonly [index: number]: number | null | undefined; readonly length: number };

function at(column: Column | undefined, index: number): number {
  const value = column?.[index];
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : 0;
}

/** Временная модуляция СРАЗУ В ДЕЦИБЕЛАХ: единичное среднее в линейных величинах
 *  смещает среднее по Йенсену, и полотно расходится с колонкой дельты. */
function modulationDb(timeNorm: number, freq: number, ampDb: number): number {
  // Фаза ОБЩАЯ для обеих сессий: флуктуации сети коррелированы, и разность трасс
  // обязана зависеть только от разницы амплитуд.
  const phase = Math.sin(freq * 0.0004) * Math.PI;
  return ampDb * Math.cos(2 * Math.PI * timeNorm * TIME_PERIODS + phase);
}

/** У сравнения демпфированный пик «дышит» сильнее — это и видно во времени. */
function amplitudeB(freq: number): number {
  const bell = Math.exp(-(((freq - DAMPED_HZ) / 3000) ** 2));
  return 1.3 + 1.9 * bell;
}

export interface SpectrogramV6 {
  /** Полотно вида «Спектрограмма»; видимость управляется классом на панели. */
  readonly host: HTMLElement;
  /** Органы управления; едут в шапку панели спектра, чтобы не тратить высоту. */
  readonly bar: HTMLElement;
  attach(plot: uPlot): void;
  redraw(): void;
}

export function buildSpectrogramV6(): SpectrogramV6 {
  const data = buildSpectrumData();
  const freqColumn = data[0] as Column | undefined;
  const columnA = data[1] as Column | undefined;
  const columnB = data[2] as Column | undefined;
  const durationS = METRICS.durationS;

  // По умолчанию — уровень сравнения; дельта — в один клик и числом в таблице.
  let mode: Mode = "b";
  // Домен частот захватывается у шкалы спектра: виды делят одну шкалу.
  let logMin = Math.log10(FREQ_TICKS[0]);
  let logMax = Math.log10(FREQ_TICKS[FREQ_TICKS.length - 1]);

  // Позиции тиков — правилом стиль-листа: разметка витрин свободна от inline-стилей
  // (§2.5, контракт S13).
  const sheet = new CSSStyleSheet();
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];

  const canvas = h("canvas", "gram-canvas", { "data-spectrogram-canvas": "" });
  // В покое показания пусты: приглашение «наведите» переполняло шапку и резало шкалу.
  const readout = h("span", "gram-readout num", { "data-spectrogram-readout": "" });
  const scale = h("span", "gram-scale", { "data-spectrogram-scale": "" });
  const ticksRow = h("div", "gram-freq-ticks", { "data-gram-freq-ticks": "", "aria-hidden": "true" });

  function freqAt(cssX: number, cssWidth: number): number {
    return 10 ** (logMin + clamp01(cssX / cssWidth) * (logMax - logMin));
  }

  function paintTicks(): void {
    ticksRow.replaceChildren(
      ...FREQ_TICKS.map((hz) =>
        h("span", "gram-freq-tick num", { "data-hz": String(hz) }, [hz.toLocaleString("en-US")]),
      ),
    );
    sheet.replaceSync(
      FREQ_TICKS.map((hz) => {
        const t = ((Math.log10(hz) - logMin) / (logMax - logMin)) * 100;
        return `.app-v6 [data-hz="${hz}"]{left:${t.toFixed(2)}%}`;
      }).join(""),
    );
  }

  /** Ближайший индекс частоты — сетка спектра неравномерна по пикселям. */
  function indexAt(freq: number): number {
    const length = freqColumn?.length ?? 0;
    if (length === 0) return 0;
    let low = 0;
    let high = length - 1;
    while (high - low > 1) {
      const mid = (low + high) >> 1;
      if (at(freqColumn, mid) < freq) low = mid;
      else high = mid;
    }
    return Math.abs(at(freqColumn, low) - freq) <= Math.abs(at(freqColumn, high) - freq)
      ? low
      : high;
  }

  /** Значение полотна в дБ: уровень трассы либо отношение трасс. */
  function valueAt(freq: number, timeNorm: number): number {
    const index = indexAt(freq);
    const a = at(columnA, index);
    const b = at(columnB, index);
    if (a <= 0 || b <= 0) return mode === "delta" ? 0 : -120;
    const aDb = 10 * Math.log10(a) + modulationDb(timeNorm, freq, 1.3);
    const bDb = 10 * Math.log10(b) + modulationDb(timeNorm, freq, amplitudeB(freq));
    if (mode === "delta") return bDb - aDb;
    return mode === "a" ? aDb : bDb;
  }

  function levelRange(): { low: number; high: number } {
    let low = Number.POSITIVE_INFINITY;
    let high = Number.NEGATIVE_INFINITY;
    const column = mode === "a" ? columnA : columnB;
    for (let index = 0; index < (column?.length ?? 0); index += 1) {
      const value = at(column, index);
      if (value <= 0) continue;
      const db = 10 * Math.log10(value);
      if (db < low) low = db;
      if (db > high) high = db;
    }
    return Number.isFinite(low) ? { low, high } : { low: -90, high: -30 };
  }

  function paintScale(): void {
    if (mode === "delta") {
      scale.textContent = `−${DELTA_SPAN_DB} … +${DELTA_SPAN_DB} дБ`;
      return;
    }
    const { low, high } = levelRange();
    scale.textContent = `${Math.round(low)} … ${Math.round(high)} дБ`;
  }

  function redraw(): void {
    const box = canvas.getBoundingClientRect();
    const cssWidth = Math.round(box.width);
    const cssHeight = Math.round(box.height);
    if (cssWidth <= 0 || cssHeight <= 0) return;

    // Буфер — в ФИЗИЧЕСКИХ пикселях: иначе браузер растягивает полотно
    // интерполяцией на любом экране с масштабированием, отличным от 100%.
    const ratio = devicePixelRatio || 1;
    const width = Math.round(cssWidth * ratio);
    const height = Math.round(cssHeight * ratio);
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return;

    const image = ctx.createImageData(width, height);
    const { low, high } = levelRange();
    const span = high - low || 1;
    for (let x = 0; x < width; x += 1) {
      // Частота — по CSS-координате собственной лог-шкалы вида.
      const freq = freqAt(x / ratio, cssWidth);
      for (let y = 0; y < height; y += 1) {
        // Время растёт сверху вниз: верх полотна — начало записи.
        const timeNorm = Math.floor((y / height) * TIME_BINS) / TIME_BINS;
        const value = valueAt(freq, timeNorm);
        const rgb = mode === "delta" ? deltaColor(value) : heatColor((value - low) / span);
        const offset = (y * width + x) * 4;
        image.data[offset] = rgb[0];
        image.data[offset + 1] = rgb[1];
        image.data[offset + 2] = rgb[2];
        image.data[offset + 3] = 255;
      }
    }
    ctx.putImageData(image, 0, 0);
    paintScale();
  }

  const modes = h("div", "gram-modes", { role: "group", "aria-label": "Содержимое спектрограммы" });
  const buttons = new Map<Mode, HTMLElement>();
  for (const key of ["a", "b", "delta"] as const) {
    const button = h(
      "button",
      "btn-quiet gram-mode",
      { type: "button", "data-spectrogram-mode": key, "aria-pressed": String(key === mode) },
      [MODE_TITLE[key]],
    );
    button.addEventListener("click", () => {
      mode = key;
      for (const [name, node] of buttons) node.setAttribute("aria-pressed", String(name === key));
      redraw();
    });
    buttons.set(key, button);
    modes.append(button);
  }

  canvas.addEventListener("mousemove", (event) => {
    const box = canvas.getBoundingClientRect();
    const x = event.clientX - box.left;
    const timeNorm = clamp01((event.clientY - box.top) / box.height);
    const freq = freqAt(x, box.width);
    const value = valueAt(freq, Math.floor(timeNorm * TIME_BINS) / TIME_BINS);
    const seconds = (timeNorm * durationS).toFixed(2);
    const sign = mode === "delta" && value > 0 ? "+" : "";
    readout.textContent = `${formatHz(freq)} · ${seconds} с · ${sign}${value.toFixed(1)} дБ`;
  });
  canvas.addEventListener("mouseleave", () => {
    readout.textContent = "наведите на полотно";
  });

  const bar = h("div", "gram-bar", {}, [modes, readout, scale]);
  // Шкала времени: верх полотна — начало записи, низ — конец.
  const axis = h("div", "gram-axis", { "aria-hidden": "true" }, [
    h("span", "gram-tick num", {}, ["0 с"]),
    h("span", "gram-tick num", {}, [`${(durationS / 2).toFixed(1)} с`]),
    h("span", "gram-tick num", {}, [`${durationS.toFixed(1)} с`]),
  ]);
  const wrap = h("div", "gram-canvas-wrap", {}, [axis, canvas]);
  const host = h("div", "gram", { "data-spectrogram": "" }, [wrap, ticksRow]);

  // Полотно тянется flex-ом: перерисовка при любом изменении размера окна вида.
  const observer = new ResizeObserver(() => redraw());
  observer.observe(wrap);

  return {
    host,
    bar,
    attach(plot) {
      const scaleX = plot.scales.x;
      if (typeof scaleX?.min === "number" && scaleX.min > 0) logMin = Math.log10(scaleX.min);
      if (typeof scaleX?.max === "number" && scaleX.max > 0) logMax = Math.log10(scaleX.max);
      paintTicks();
      redraw();
    },
    redraw,
  };
}
