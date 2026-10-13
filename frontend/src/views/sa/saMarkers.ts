/** Маркеры SA (Todo 15): клиентская разметка живого спектра — до 4
 * маркеров пользователя (клик по полю графика → частота) с отсчётом
 * уровня по живой трассе склада: максимум ±1 бин, затем параболический
 * подъём в дБ (порт lnt/markers.py и readoutAt инспекции — вход уже в
 * дБ, логарифмировать не надо). Маркеры живут только на клиенте: на
 * сервер не уходят никогда. Пики поиска — снимок peaks[] свипа (сервер
 * уже отобрал максимумы полной сетки по prominence); q_factor=null →
 * NaN, чтобы полоса FWHM не рисовалась (bandBounds отбрасывает его). */

import type { LiveSaPeak } from "../../api/types-live";
import type { ChartPeak } from "../../components/charts/types";

export const SA_MARKER_LIMIT = 4;

export interface SaMarkerReadout {
  readonly frequencyHz: number;
  readonly levelDb: number;
}

export interface SaMarker {
  readonly id: number;
  readonly frequencyHz: number;
  readonly levelDb: number;
}

/** След для отсчёта: сетка частот и уровни дБ трассы склада. */
export interface SaMarkerTrace {
  readonly freq: ArrayLike<number>;
  readonly psdDb: ArrayLike<number>;
}

export type SaMarkerRejectReason = "limit" | "no-trace";

export type SaMarkerPlacement =
  | { kind: "placed"; marker: SaMarker }
  | { kind: "rejected"; reason: SaMarkerRejectReason };

/** Отсчёт в точке: ближайший бин → максимум ±1 бин → парабола в дБ.
 * null — пустой вход или мусорная цель; выдуманных уровней не бывает. */
export function readoutDbAt(
  freq: ArrayLike<number>,
  psdDb: ArrayLike<number>,
  frequencyHz: number,
): SaMarkerReadout | null {
  const count = Math.min(freq.length, psdDb.length);
  if (count === 0 || !Number.isFinite(frequencyHz)) return null;
  let nearest = -1;
  let best = Number.POSITIVE_INFINITY;
  for (let i = 0; i < count; i += 1) {
    const binFreq = freq[i] ?? Number.NaN;
    if (!Number.isFinite(binFreq)) continue;
    const gap = Math.abs(binFreq - frequencyHz);
    if (gap < best) {
      best = gap;
      nearest = i;
    }
  }
  if (nearest < 0) return null;
  let center = nearest;
  for (let i = Math.max(0, nearest - 1); i <= Math.min(count - 1, nearest + 1); i += 1) {
    if ((psdDb[i] ?? Number.NEGATIVE_INFINITY) > (psdDb[center] ?? Number.NEGATIVE_INFINITY)) {
      center = i;
    }
  }
  const level = psdDb[center];
  const binFreq = freq[center];
  if (level === undefined || !Number.isFinite(level)) return null;
  if (binFreq === undefined || !Number.isFinite(binFreq)) return null;
  if (center === 0 || center >= count - 1) return { frequencyHz: binFreq, levelDb: level };
  const prev = psdDb[center - 1];
  const next = psdDb[center + 1];
  if (
    prev === undefined ||
    next === undefined ||
    !Number.isFinite(prev) ||
    !Number.isFinite(next)
  ) {
    return { frequencyHz: binFreq, levelDb: level };
  }
  const denominator = prev - 2 * level + next;
  if (denominator >= 0) return { frequencyHz: binFreq, levelDb: level };
  const deltaBins = Math.max(-0.5, Math.min(0.5, (0.5 * (prev - next)) / denominator));
  const gainDb = Math.max(0, -0.25 * (prev - next) * deltaBins);
  const nextFreq = freq[center + 1];
  if (nextFreq === undefined || !(nextFreq - binFreq > 0)) {
    return { frequencyHz: binFreq, levelDb: level + gainDb };
  }
  const step = nextFreq - binFreq;
  return { frequencyHz: binFreq + deltaBins * step, levelDb: level + gainDb };
}

/** Состояние маркеров пользователя: лимит 4, отказы с причиной. */
export class SaMarkers {
  private seq = 0;
  private readonly items: SaMarker[] = [];

  /** Постановка маркера; отказ — лимит или отсутствие трассы. */
  place(trace: SaMarkerTrace | null, frequencyHz: number): SaMarkerPlacement {
    if (this.items.length >= SA_MARKER_LIMIT) return { kind: "rejected", reason: "limit" };
    const readout = trace === null ? null : readoutDbAt(trace.freq, trace.psdDb, frequencyHz);
    if (readout === null) return { kind: "rejected", reason: "no-trace" };
    this.seq += 1;
    const marker: SaMarker = {
      id: this.seq,
      frequencyHz: readout.frequencyHz,
      levelDb: readout.levelDb,
    };
    this.items.push(marker);
    return { kind: "placed", marker };
  }

  clear(): void {
    this.items.length = 0;
  }

  list(): readonly SaMarker[] {
    return [...this.items];
  }
}

/** Пики свипа → аннотации графика (как peaksFromDetail инспекции);
 * порядок сервера (prominence по убыванию) сохраняется. */
export function peaksFromSweep(peaks: readonly LiveSaPeak[]): ChartPeak[] {
  const result: ChartPeak[] = [];
  for (const peak of peaks) {
    if (!Number.isFinite(peak.frequency_hz) || !Number.isFinite(peak.level_db)) continue;
    result.push({
      frequency_hz: peak.frequency_hz,
      level_db: peak.level_db,
      prominence_db: Number.isFinite(peak.prominence_db) ? peak.prominence_db : 0,
      q_factor: peak.q_factor ?? Number.NaN,
    });
  }
  return result;
}
