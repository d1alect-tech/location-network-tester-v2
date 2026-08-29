/** Разница между трассами графика в точках пиков (V6).
 *
 *  Считается как 10·lg(Б/А) — чистое отношение двух нарисованных PSD. Именно оно
 *  осмысленно по протоколу продукта («сравнивать дельты, не абсолюты») и не
 *  смешивает синтетику графика с абсолютными числами из metrics.json. */
import { PEAKS } from "../showcase-redesign/data";
import { buildSpectrumData } from "../showcase-redesign/spectrum";

export interface PeakDelta {
  readonly index: number;
  readonly frequencyHz: number;
  /** Б − А в децибелах: отрицательное значение — пик подавлен. */
  readonly deltaDb: number;
}

/** Колонка uPlot: обычный массив, типизированный массив или дырявый ряд с null. */
type Column = {
  readonly [index: number]: number | null | undefined;
  readonly length: number;
};

function at(column: Column | null | undefined, index: number): number | undefined {
  if (column === null || column === undefined) return undefined;
  const value = column[index];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function nearestIndex(freq: Column | null | undefined, target: number): number {
  if (freq === null || freq === undefined) return 0;
  let best = 0;
  let bestDiff = Number.POSITIVE_INFINITY;
  for (let i = 0; i < freq.length; i++) {
    const value = at(freq, i);
    if (value === undefined) continue;
    const diff = Math.abs(value - target);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = i;
    }
  }
  return best;
}

export function buildPeakDeltas(): PeakDelta[] {
  const data = buildSpectrumData();
  const freq = data[0];
  const traceA = data[1];
  const traceB = data[2];
  return PEAKS.map((peak, index) => {
    const at0 = nearestIndex(freq, peak.frequencyHz);
    const a = at(traceA, at0);
    const b = at(traceB, at0);
    const deltaDb =
      a !== undefined && b !== undefined && a > 0 && b > 0 ? 10 * Math.log10(b / a) : 0;
    return { index, frequencyHz: peak.frequencyHz, deltaDb };
  });
}
