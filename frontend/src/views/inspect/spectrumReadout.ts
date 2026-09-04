/** B3 readout маркеров: max-агрегация ±1 бин + парабола в дБ (порт lnt/markers.py).
 * Уровни — дБ отн. 1 В²/Гц; форматтеры ru-RU общие для селекторов и таблицы. */

import type { SpectrumPayload } from "../../api/types-plots";

export const DB_REF_LABEL = "дБ (отн. 1 В²/Гц)";

export const ruHz = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });
export const ruDb = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});

export interface MarkerReadout {
  readonly frequencyHz: number;
  readonly levelDb: number;
}

export interface MarkersPaintSource {
  readonly payloadA: SpectrumPayload;
  readonly payloadB: SpectrumPayload | null;
  readonly analysis: unknown;
}

/** Уточнённый readout: максимум ±1 бин, затем парабола в дБ; null — битые данные. */
export function readoutAt(payload: SpectrumPayload, frequencyHz: number): MarkerReadout | null {
  const count = Math.min(payload.frequency_hz.length, payload.psd_v2_per_hz.length);
  if (count === 0 || !Number.isFinite(frequencyHz)) return null;
  let nearest = 0;
  let best = Number.POSITIVE_INFINITY;
  for (let i = 0; i < count; i += 1) {
    const f = payload.frequency_hz[i] ?? Number.NaN;
    const gap = Math.abs(f - frequencyHz);
    if (Number.isFinite(f) && gap < best) {
      best = gap;
      nearest = i;
    }
  }
  if (!Number.isFinite(best)) return null;
  let center = nearest;
  for (let i = Math.max(0, nearest - 1); i <= Math.min(count - 1, nearest + 1); i += 1) {
    const candidate = payload.psd_v2_per_hz[i] ?? 0;
    const current = payload.psd_v2_per_hz[center] ?? 0;
    if (candidate > current) center = i;
  }
  const psd = payload.psd_v2_per_hz[center] ?? Number.NaN;
  const freq = payload.frequency_hz[center] ?? Number.NaN;
  if (!(psd > 0) || !Number.isFinite(freq)) return null;
  if (center === 0 || center >= count - 1) {
    return { frequencyHz: freq, levelDb: 10 * Math.log10(psd) };
  }
  const prev = payload.psd_v2_per_hz[center - 1] ?? 0;
  const next = payload.psd_v2_per_hz[center + 1] ?? 0;
  if (!(prev > 0) || !(next > 0)) return { frequencyHz: freq, levelDb: 10 * Math.log10(psd) };
  const dbCenter = 10 * Math.log10(psd);
  const correction = parabolicCorrection(10 * Math.log10(prev), dbCenter, 10 * Math.log10(next));
  if (correction === null) return { frequencyHz: freq, levelDb: dbCenter };
  const step = (payload.frequency_hz[center + 1] ?? freq) - freq;
  if (!(step > 0)) return { frequencyHz: freq, levelDb: dbCenter + correction.gainDb };
  return {
    frequencyHz: freq + correction.deltaBins * step,
    levelDb: dbCenter + correction.gainDb,
  };
}

/** Δ A−B в дБ на одной частоте; null — нет трассы B или битые данные. */
export function deltaAt(
  payloadA: SpectrumPayload,
  payloadB: SpectrumPayload | null,
  frequencyHz: number,
): number | null {
  if (payloadB === null) return null;
  const a = readoutAt(payloadA, frequencyHz);
  const b = readoutAt(payloadB, frequencyHz);
  if (a === null || b === null) return null;
  return b.levelDb - a.levelDb;
}

function parabolicCorrection(
  dbMinus: number,
  dbCenter: number,
  dbPlus: number,
): { deltaBins: number; gainDb: number } | null {
  if (![dbMinus, dbCenter, dbPlus].every(Number.isFinite)) return null;
  const denominator = dbMinus - 2 * dbCenter + dbPlus;
  if (denominator >= 0) return null;
  const raw = (0.5 * (dbMinus - dbPlus)) / denominator;
  const deltaBins = Math.max(-0.5, Math.min(0.5, raw));
  return { deltaBins, gainDb: Math.max(0, -0.25 * (dbMinus - dbPlus) * deltaBins) };
}
