/** Отрисовка линий курсоров осциллографа на канвасе uPlot (выделено из
 * scopeCursorSection, лимит 250 чистых LOC; паттерн
 * annotations.createPeaksPlugin): T — вертикали на доле окна X, V —
 * горизонтали по вольтам оси Y. Цвета — только токены v2 через computed
 * style с фолбэком (паттерн charts/theme). */

import type uPlot from "uplot";
import type { CursorPositions } from "./scopeCursorModel";
import { clampFraction } from "./scopeCursors";

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

/** Линии курсоров в координатах uPlot (паттерн createPeaksPlugin):
 * T — вертикали на доле окна X, V — горизонтали по вольтам оси Y. */
export function drawCursorLines(self: uPlot, readPositions: () => CursorPositions): void {
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
    const x = self.valToPos(xValue, "x", true);
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
    const y = self.valToPos(volts, "y", true);
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
