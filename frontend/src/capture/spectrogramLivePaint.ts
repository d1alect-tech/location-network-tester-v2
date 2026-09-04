/** Покадровая отрисовка live-спектрограммы: полотно в физических пикселях,
 * палитра витрины (heat для уровней, delta для отклонений). Без DOM-хрома. */

import {
  DELTA_SPAN_DB,
  clamp01,
  deltaColor,
  heatColor,
} from "../showcase-round2/spectrogramPalette";
import {
  FREQ_BINS,
  type LiveGramMode,
  type LiveGramStore,
  TIME_BINS,
} from "./spectrogramLiveStore";

/** Подпись шкалы в формате витрины: уровень — дБВ/Гц с опорой, дельта — дБ. */
export function gramScaleText(mode: LiveGramMode, range: { low: number; high: number }): string {
  if (mode === "delta") return `−${DELTA_SPAN_DB} … +${DELTA_SPAN_DB} дБ`;
  return `${Math.round(range.low)} … ${Math.round(range.high)} дБВ/Гц (отн. 1 В²/Гц)`;
}

function pixelRatio(): number {
  return typeof devicePixelRatio === "number" && devicePixelRatio > 0 ? devicePixelRatio : 1;
}

/** Рисует кольцо store на canvas; пропускает кадр без размеров и ctx. */
export function paintGramFrame(
  canvas: HTMLCanvasElement,
  store: LiveGramStore,
  mode: LiveGramMode,
): void {
  const box = canvas.getBoundingClientRect();
  const cssWidth = Math.round(box.width);
  const cssHeight = Math.round(box.height);
  if (cssWidth <= 0 || cssHeight <= 0) return;
  const ratio = pixelRatio();
  const width = Math.round(cssWidth * ratio);
  const height = Math.round(cssHeight * ratio);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (ctx === null) return;

  const { low, high } = store.levelRange();
  const span = high - low || 1;
  const count = store.columnCount();
  const image = ctx.createImageData(width, height);
  for (let x = 0; x < width; x += 1) {
    const t = clamp01(x / ratio / cssWidth);
    const bin = Math.min(FREQ_BINS - 1, Math.floor(t * FREQ_BINS));
    for (let y = 0; y < height; y += 1) {
      // Время растёт сверху вниз: верх полотна — старейшая колонка.
      const timeNorm = Math.floor((y / height) * TIME_BINS) / TIME_BINS;
      const k = count === 0 ? 0 : Math.min(count - 1, Math.floor(timeNorm * count));
      const row = count === 0 ? 0 : store.rowPhysical(k);
      const value = store.valueAt(bin, row, mode);
      const rgb = mode === "delta" ? deltaColor(value) : heatColor((value - low) / span);
      const offset = (y * width + x) * 4;
      image.data[offset] = rgb[0];
      image.data[offset + 1] = rgb[1];
      image.data[offset + 2] = rgb[2];
      image.data[offset + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
}
