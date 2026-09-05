/** Отрисовка маски поверх uPlot: лимит, бледный margin-штрих и янтарная
 *  подсветка только нарушенного сегмента трассы A (паттерн Keysight, бриф #13). */
import type uPlot from "uplot";

/** Плоскость графика: лимит и margin в линейном PSD генератора витрин. */
const BAND_LOW_HZ = 18000;
const BAND_HIGH_HZ = 28000;
const LIMIT_LINEAR = 1.0e-6;
const MARGIN_LINEAR = 7.0e-7;

function colorVar(u: uPlot, name: string, fallback: string): string {
  const value = getComputedStyle(u.root).getPropertyValue(name).trim();
  return value === "" ? fallback : value;
}

function segment(u: uPlot, level: number): { x0: number; x1: number; y: number } {
  return {
    x0: u.valToPos(BAND_LOW_HZ, "x", true),
    x1: u.valToPos(BAND_HIGH_HZ, "x", true),
    y: u.valToPos(level, "y", true),
  };
}

function drawLine(
  ctx: CanvasRenderingContext2D,
  seg: { x0: number; x1: number; y: number },
  stroke: string,
  dash: readonly number[],
): void {
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1.5;
  ctx.setLineDash([...dash]);
  ctx.beginPath();
  ctx.moveTo(seg.x0, seg.y);
  ctx.lineTo(seg.x1, seg.y);
  ctx.stroke();
}

function drawViolation(u: uPlot, ctx: CanvasRenderingContext2D, viol: string): void {
  const freq = u.data[0];
  const psdA = u.data[1];
  if (freq === undefined || psdA === undefined) return;
  ctx.strokeStyle = viol;
  ctx.lineWidth = 3.5;
  ctx.setLineDash([]);
  let open = false;
  ctx.beginPath();
  for (let i = 0; i < freq.length; i++) {
    const f = freq[i];
    const v = psdA[i];
    if (typeof f !== "number" || typeof v !== "number") continue;
    const inside = f >= BAND_LOW_HZ && f <= BAND_HIGH_HZ && v > LIMIT_LINEAR;
    if (inside) {
      const x = u.valToPos(f, "x", true);
      const y = u.valToPos(v, "y", true);
      if (open) ctx.lineTo(x, y);
      else ctx.moveTo(x, y);
      open = true;
    } else if (open) {
      ctx.stroke();
      ctx.beginPath();
      open = false;
    }
  }
  if (open) ctx.stroke();
}

/** Хук draw для renderSpectrum: маска рисуется после трасс, поверх. */
export function drawLimitMask(u: uPlot): void {
  const ctx = u.ctx;
  ctx.save();
  drawLine(ctx, segment(u, LIMIT_LINEAR), colorVar(u, "--r3-limit", "#ef5b62"), []);
  drawLine(
    ctx,
    segment(u, MARGIN_LINEAR),
    colorVar(u, "--r3-margin", "rgba(239,91,98,0.45)"),
    [5, 4],
  );
  drawViolation(u, ctx, colorVar(u, "--r3-viol", "#ffb03a"));
  ctx.restore();
}
