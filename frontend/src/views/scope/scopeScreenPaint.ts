/** Живопись экрана осциллографа (Todo 11): послесвечение — канвас-слой ПОД
 * волной (uPlot-развёртка тодо 8 встанет поверх трассы), трасса кадра —
 * полилинии CH1/CH2 поверх секции сетки. Цвета — только токены v2 через
 * computed style с фолбэком (паттерн deltaStrip.cssVar): палитра
 * showcase-round2 НЕ импортируется. DPR-aware, как paintGramFrame;
 * без размеров/контекста кадр пропускается молча (jsdom). */

import type { ScopeHistoryFrame, ScopeHistorySeries } from "./scopeHistory";
import type { ScopePersistence } from "./scopePersistence";
import { PERSISTENCE_GRID_H, PERSISTENCE_GRID_W } from "./scopePersistence";

export interface Rgb {
  readonly r: number;
  readonly g: number;
  readonly b: number;
}

const HEX_SHORT = /^#([0-9a-f]{3})$/i;
const HEX_LONG = /^#([0-9a-f]{6})$/i;

/** «#abc» / «#aabbcc» → RGB; прочее — null. */
export function parseHexColor(hex: string): Rgb | null {
  const text = hex.trim();
  if (HEX_LONG.test(text)) {
    return {
      r: Number.parseInt(text.slice(1, 3), 16),
      g: Number.parseInt(text.slice(3, 5), 16),
      b: Number.parseInt(text.slice(5, 7), 16),
    };
  }
  const short = HEX_SHORT.exec(text);
  if (short !== null) {
    const digits = (short[1] as string).split("");
    return {
      r: 17 * Number.parseInt(digits[0] as string, 16),
      g: 17 * Number.parseInt(digits[1] as string, 16),
      b: 17 * Number.parseInt(digits[2] as string, 16),
    };
  }
  return null;
}

/** Альфа свечения ячейки: уровень 0..255 → 0..1. */
export function afterglowAlpha(level: number): number {
  const alpha = level / 255;
  return alpha < 0 ? 0 : alpha > 1 ? 1 : alpha;
}

/** Токен из computed style (фолбэк — значение токена из v2-tokens.css). */
export function cssTokenColor(host: HTMLElement, token: string, fallback: string): Rgb {
  const value = getComputedStyle(host).getPropertyValue(token).trim();
  return parseHexColor(value) ?? (parseHexColor(fallback) as Rgb);
}

function pixelRatio(): number {
  return typeof devicePixelRatio === "number" && devicePixelRatio > 0 ? devicePixelRatio : 1;
}

function fitCanvas(canvas: HTMLCanvasElement): { width: number; height: number } | null {
  const box = canvas.getBoundingClientRect();
  const cssWidth = Math.round(box.width);
  const cssHeight = Math.round(box.height);
  if (cssWidth <= 0 || cssHeight <= 0) return null;
  const ratio = pixelRatio();
  canvas.width = Math.round(cssWidth * ratio);
  canvas.height = Math.round(cssHeight * ratio);
  return { width: canvas.width, height: canvas.height };
}

/** Слой послесвечения: ячейки аккумулятора → полупрозрачные прямоугольники
 * цвета --lnt-accent; стиль кэшируется по уровню, нулевые ячейки пропускаются. */
export function paintScopePersistence(canvas: HTMLCanvasElement, store: ScopePersistence): void {
  const size = fitCanvas(canvas);
  if (size === null) return;
  const ctx = canvas.getContext("2d");
  if (ctx === null) return;
  ctx.clearRect(0, 0, size.width, size.height);
  const color = cssTokenColor(canvas, "--lnt-accent", "#5681ff");
  const styles: string[] = [];
  for (let level = 1; level <= 255; level += 1) {
    styles[level] = `rgba(${color.r}, ${color.g}, ${color.b}, ${afterglowAlpha(level).toFixed(3)})`;
  }
  const cellW = size.width / PERSISTENCE_GRID_W;
  const cellH = size.height / PERSISTENCE_GRID_H;
  const drawW = Math.max(1, Math.ceil(cellW));
  const drawH = Math.max(1, Math.ceil(cellH));
  for (let y = 0; y < PERSISTENCE_GRID_H; y += 1) {
    const pixelY = y * cellH;
    for (let x = 0; x < PERSISTENCE_GRID_W; x += 1) {
      const level = store.levelAt(x, y);
      if (level <= 0) continue;
      ctx.fillStyle = styles[level] as string;
      ctx.fillRect(x * cellW, pixelY, drawW, drawH);
    }
  }
}

/** Трасса кадра: секция сетки (--lnt-line) + CH1 цветом A (--lnt-a) и
 * CH2 цветом B (--lnt-b), семантика пары DESIGN.md. null — только сетка. */
export function paintScopeTrace(
  canvas: HTMLCanvasElement,
  frame: ScopeHistoryFrame | null,
  voltsSpan: number,
): void {
  const size = fitCanvas(canvas);
  if (size === null) return;
  const ctx = canvas.getContext("2d");
  if (ctx === null) return;
  ctx.clearRect(0, 0, size.width, size.height);
  const line = cssTokenColor(canvas, "--lnt-line", "#33383f");
  ctx.strokeStyle = `rgba(${line.r}, ${line.g}, ${line.b}, 0.4)`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 1; i < 10; i += 1) {
    const x = (i / 10) * size.width;
    ctx.moveTo(x, 0);
    ctx.lineTo(x, size.height);
  }
  for (let i = 1; i < 6; i += 1) {
    const y = (i / 6) * size.height;
    ctx.moveTo(0, y);
    ctx.lineTo(size.width, y);
  }
  ctx.stroke();
  if (frame === null) return;
  drawSeries(ctx, canvas, size, frame.ch1, "--lnt-a", "#3ec9e6", voltsSpan);
  drawSeries(ctx, canvas, size, frame.ch2, "--lnt-b", "#e6a13c", voltsSpan);
}

function drawSeries(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  size: { width: number; height: number },
  series: ScopeHistorySeries,
  token: string,
  fallback: string,
  voltsSpan: number,
): void {
  const timeS = series.timeS;
  const volts = series.voltageV;
  if (timeS.length < 2 || voltsSpan <= 0) return;
  const color = cssTokenColor(canvas, token, fallback);
  const tMin = timeS[0] as number;
  const tSpan = (timeS[timeS.length - 1] as number) - tMin || 1e-9;
  ctx.strokeStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < timeS.length; i += 1) {
    const v = volts[i] as number;
    if (!Number.isFinite(v)) continue;
    const x = (((timeS[i] as number) - tMin) / tSpan) * size.width;
    const y = (0.5 - v / voltsSpan) * size.height;
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}
