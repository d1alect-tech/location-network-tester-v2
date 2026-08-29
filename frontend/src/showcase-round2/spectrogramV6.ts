/** Спектрограмма V6 — вторая дорожка под линейным спектром.
 *
 *  В продукте спектрограмма и спектр живут порознь: своя сессия, свой зум, общей
 *  шкалы нет. Здесь полотно стоит ровно под областью данных графика и берёт частоту
 *  каждой своей колонки у самого uPlot, поэтому шкала совпадает по построению.
 *  Ось X — частота (общая со спектром), ось Y — время записи.
 *
 *  Содержимое переключается А / Б / Δ: единица работы V6 — пара, поэтому по
 *  умолчанию открыта разница, показывающая, где именно во времени разошлись трассы. */
import type uPlot from "uplot";

import { METRICS, formatHz } from "../showcase-redesign/data";
import { buildSpectrumData } from "../showcase-redesign/spectrum";
import { h } from "./kit";

type Mode = "a" | "b" | "delta";

const TIME_BINS = 56;
const DELTA_SPAN_DB = 8;
const DAMPED_HZ = 22418;

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

/** Временная модуляция с единичным средним: усреднение по времени возвращает трассу. */
function modulation(timeNorm: number, freq: number, amp: number, seed: number): number {
  const phase = Math.sin(freq * 0.0004 + seed) * Math.PI;
  return 1 + amp * Math.cos(2 * Math.PI * timeNorm * 3 + phase);
}

/** У сравнения демпфированный пик «дышит» сильнее — это и видно во времени. */
function amplitudeB(freq: number): number {
  const bell = Math.exp(-(((freq - DAMPED_HZ) / 3000) ** 2));
  return 0.3 + 0.42 * bell;
}

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/** Тепловая шкала уровня: тёмный синий → бирюзовый → песочный. */
function heatColor(unit: number): [number, number, number] {
  const t = clamp01(unit);
  if (t < 0.5) {
    const k = t * 2;
    return [Math.round(18 + 12 * k), Math.round(26 + 96 * k), Math.round(54 + 78 * k)];
  }
  const k = (t - 0.5) * 2;
  return [Math.round(30 + 200 * k), Math.round(122 + 78 * k), Math.round(132 - 42 * k)];
}

/** Расходящаяся шкала дельты в цветах самих трасс: синий — тише, оранжевый — громче. */
function deltaColor(db: number): [number, number, number] {
  const t = clamp01(Math.abs(db) / DELTA_SPAN_DB);
  const base: [number, number, number] = db < 0 ? [86, 129, 255] : [230, 134, 25];
  return [
    Math.round(29 + (base[0] - 29) * t),
    Math.round(29 + (base[1] - 29) * t),
    Math.round(29 + (base[2] - 29) * t),
  ];
}

export interface SpectrogramV6 {
  /** Полотно; встаёт под графиком внутри той же панели. */
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

  let mode: Mode = "delta";
  let plot: uPlot | undefined;
  // Позиция полотна публикуется правилом стиль-листа: разметка витрин свободна
  // от inline-стилей (§2.5, контракт S13).
  const sheet = new CSSStyleSheet();
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];

  const canvas = h("canvas", "gram-canvas", { "data-spectrogram-canvas": "" });
  // В покое показания пусты: приглашение «наведите» переполняло шапку и резало шкалу.
  const readout = h("span", "gram-readout num", { "data-spectrogram-readout": "" });
  const scale = h("span", "gram-scale", { "data-spectrogram-scale": "" });

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
    const a = at(columnA, index) * modulation(timeNorm, freq, 0.3, 0.7);
    const b = at(columnB, index) * modulation(timeNorm, freq, amplitudeB(freq), 2.1);
    if (mode === "delta") return a > 0 && b > 0 ? 10 * Math.log10(b / a) : 0;
    const level = mode === "a" ? a : b;
    return level > 0 ? 10 * Math.log10(level) : -120;
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
    const current = plot;
    if (current === undefined) return;
    // Геометрию берём у самой области данных, а не из bbox: внутренние отступы
    // обёртки графика иначе сдвигают полотно относительно шкалы.
    const over = current.over.getBoundingClientRect();
    const wrap = canvas.parentElement?.getBoundingClientRect();
    if (wrap === undefined) return;
    const width = Math.round(over.width);
    const left = Math.round(over.left - wrap.left);
    // Зазор под осью Y графика занимает шкала времени, а не пустота.
    sheet.replaceSync(`.app-v6 .gram-axis{width:${left}px}.app-v6 .gram-canvas{width:${width}px}`);
    const height = Math.round(canvas.getBoundingClientRect().height);
    if (width <= 0 || height <= 0) return;

    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return;

    const image = ctx.createImageData(width, height);
    const { low, high } = levelRange();
    const span = high - low || 1;
    for (let x = 0; x < width; x += 1) {
      const freq = current.posToVal(x, "x");
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
    const current = plot;
    if (current === undefined) return;
    const box = canvas.getBoundingClientRect();
    const x = event.clientX - box.left;
    const timeNorm = clamp01((event.clientY - box.top) / box.height);
    const freq = current.posToVal(x, "x");
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
  const host = h("div", "gram", { "data-spectrogram": "" }, [
    h("div", "gram-canvas-wrap", {}, [axis, canvas]),
  ]);

  return {
    host,
    bar,
    attach(instance: uPlot): void {
      plot = instance;
      redraw();
    },
    redraw,
  };
}
