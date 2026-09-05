/** Дельта-полоса под спектром: 10·log10(B/A) по тем же данным, что и трассы.
 *  Индекс данных лог-равномерен по частоте, поэтому ось X полосы совпадает
 *  с лог-осью спектра без синхронизации шкал. */
import { buildSpectrumData } from "../showcase-redesign/spectrum";
import { h } from "./kit";

const RANGE_DB = 8;

function cssVar(host: HTMLElement, name: string, fallback: string): string {
  const value = getComputedStyle(host).getPropertyValue(name).trim();
  return value === "" ? fallback : value;
}

function paint(canvas: HTMLCanvasElement): void {
  const ctx = canvas.getContext("2d");
  if (ctx === null) return;
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (width === 0 || height === 0) return;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.scale(dpr, dpr);

  const data = buildSpectrumData();
  const psdA = data[1];
  const psdB = data[2];
  if (psdA === undefined || psdB === undefined) return;
  const n = psdA.length;
  const zeroY = height / 2;
  const yFor = (db: number): number =>
    zeroY - (Math.max(-RANGE_DB, Math.min(RANGE_DB, db)) / RANGE_DB) * (height / 2 - 2);

  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = cssVar(canvas, "--r3-line", "#33383f");
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, zeroY);
  ctx.lineTo(width, zeroY);
  ctx.stroke();

  ctx.strokeStyle = cssVar(canvas, "--r3-delta", "#b7a6ff");
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const a = psdA[i];
    const b = psdB[i];
    if (typeof a !== "number" || typeof b !== "number" || !(a > 0) || !(b > 0)) continue;
    const x = (i / (n - 1)) * width;
    const y = yFor(10 * Math.log10(b / a));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}

/** Полоса Δ = B − A с подписью и шкалой ±8 дБ. */
export function buildDeltaStrip(): HTMLElement {
  const canvas = h("canvas", "delta-canvas", { "aria-hidden": "true" });
  const strip = h("div", "delta-strip", { "data-r3": "delta-strip" }, [
    h("span", "t-tag delta-strip-label", {}, ["Δ = B − A, дБ · ±8"]),
    canvas,
  ]);
  const observer = new ResizeObserver(() => paint(canvas));
  observer.observe(canvas);
  return strip;
}
