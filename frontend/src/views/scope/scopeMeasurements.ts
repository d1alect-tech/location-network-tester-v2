/** Измерения по кадру живого режима (Todo 10): чистые функции, без DOM.
 * Частота — пересечение порога по фронту, зеркально софт-триггеру
 * (instrument/trigger.py: rising — prev < level && cur >= level), время
 * пересечения уточняется линейной интерполяцией между отсчётами, как
 * sub-bin уточнение в spectrumReadout.readoutAt. Экстремумы уточняются
 * параболой по трём соседним отсчётам (та же идея уточнения пика).
 * Плоский/нулевой кадр измерений не даёт: null → «—», никогда NaN.
 * Подписи нейтральные: отсчёты 8-бит АЦП, без калибровочных заявлений. */

import type { LiveChannelSeries } from "../../api/types-live";

export interface ScopeMeasurement {
  readonly vppV: number | null;
  readonly vmaxV: number | null;
  readonly vminV: number | null;
  readonly rmsV: number | null;
  readonly frequencyHz: number | null;
  readonly periodS: number | null;
  /** Доля высокого уровня (0..1) в полном периоде. */
  readonly duty: number | null;
}

/** Отсутствие измерения: плоский сигнал, пустой канал, меньше двух фронтов. */
export const NO_MEASUREMENT: ScopeMeasurement = {
  vppV: null,
  vmaxV: null,
  vminV: null,
  rmsV: null,
  frequencyHz: null,
  periodS: null,
  duty: null,
};

interface Sample {
  readonly t: number;
  readonly v: number;
}

interface Edge {
  readonly timeS: number;
  readonly rising: boolean;
}

/** Измерения одного канала кадра. Порог фронта — уровень триггера; null —
 * середина размаха ( AUTO-кадр без триггера). */
export function measureSeries(series: LiveChannelSeries, levelV: number | null): ScopeMeasurement {
  const samples = finiteSamples(series);
  if (samples.length === 0) return NO_MEASUREMENT;

  let iMax = 0;
  let iMin = 0;
  let sumSquares = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = samples[i];
    if (sample === undefined) continue;
    if (sample.v > (samples[iMax]?.v ?? Number.NEGATIVE_INFINITY)) iMax = i;
    if (sample.v < (samples[iMin]?.v ?? Number.POSITIVE_INFINITY)) iMin = i;
    sumSquares += sample.v * sample.v;
  }
  const rawMax = samples[iMax]?.v ?? 0;
  const rawMin = samples[iMin]?.v ?? 0;
  if (rawMax === rawMin) return NO_MEASUREMENT;

  const vmaxV = refinedExtreme(samples, iMax, "max");
  const vminV = refinedExtreme(samples, iMin, "min");
  const rmsV = Math.sqrt(sumSquares / samples.length);

  const level = levelV !== null && Number.isFinite(levelV) ? levelV : (rawMax + rawMin) / 2;
  const edges = edgesAtLevel(samples, level);

  const risingTimes = edges.filter((edge) => edge.rising).map((edge) => edge.timeS);
  let periodS: number | null = null;
  let frequencyHz: number | null = null;
  if (risingTimes.length >= 2) {
    let sumIntervals = 0;
    for (let i = 1; i < risingTimes.length; i += 1) {
      const previous = risingTimes[i - 1];
      const current = risingTimes[i];
      if (previous === undefined || current === undefined) continue;
      sumIntervals += current - previous;
    }
    periodS = sumIntervals / (risingTimes.length - 1);
    frequencyHz = periodS > 0 ? 1 / periodS : null;
  }

  return {
    vppV: vmaxV - vminV,
    vmaxV,
    vminV,
    rmsV,
    frequencyHz,
    periodS,
    duty: dutyFromEdges(edges),
  };
}

/** Параболическое уточнение экстремума по трём соседним отсчётам; на краях
 * и плоских тройках — сырое значение отсчёта. */
function refinedExtreme(samples: Sample[], index: number, mode: "max" | "min"): number {
  const center = samples[index];
  const left = samples[index - 1];
  const right = samples[index + 1];
  if (center === undefined) return 0;
  if (left === undefined || right === undefined) return center.v;
  const curvature = (left.v + right.v) / 2 - center.v;
  const wantsCurvature = mode === "max" ? curvature < 0 : curvature > 0;
  if (!wantsCurvature) return center.v;
  const slope = (right.v - left.v) / 2;
  const vertex = center.v - (slope * slope) / (4 * curvature);
  if (!Number.isFinite(vertex)) return center.v;
  if (mode === "max" && vertex < center.v) return center.v;
  if (mode === "min" && vertex > center.v) return center.v;
  return vertex;
}

/** Фронты/спады на пороге: семантика зеркальна trigger.py, время — линейная
 * интерполяция до точного уровня. */
function edgesAtLevel(samples: Sample[], levelV: number): Edge[] {
  const edges: Edge[] = [];
  for (let i = 1; i < samples.length; i += 1) {
    const previous = samples[i - 1];
    const current = samples[i];
    if (previous === undefined || current === undefined) continue;
    if (previous.v < levelV && current.v >= levelV) {
      edges.push({ timeS: crossingTimeS(previous, current, levelV), rising: true });
    } else if (previous.v > levelV && current.v <= levelV) {
      edges.push({ timeS: crossingTimeS(previous, current, levelV), rising: false });
    }
  }
  return edges;
}

function crossingTimeS(previous: Sample, current: Sample, levelV: number): number {
  const dv = current.v - previous.v;
  if (dv === 0) return current.t;
  const fraction = Math.min(1, Math.max(0, (levelV - previous.v) / dv));
  return previous.t + fraction * (current.t - previous.t);
}

/** duty из полных периодов «фронт → спад → фронт»: высокий = спад − фронт,
 * низкий = следующий фронт − спад. Нет полного периода — null. */
function dutyFromEdges(edges: Edge[]): number | null {
  let highTotal = 0;
  let lowTotal = 0;
  let cycles = 0;
  let i = 0;
  while (i < edges.length) {
    if (!edges[i]?.rising) {
      i += 1;
      continue;
    }
    const rise = edges[i]?.timeS ?? 0;
    let j = i + 1;
    while (j < edges.length && edges[j]?.rising === true) j += 1;
    if (j >= edges.length) break;
    const fall = edges[j]?.timeS ?? 0;
    let k = j + 1;
    while (k < edges.length && edges[k]?.rising !== true) k += 1;
    if (k >= edges.length) break;
    const nextRise = edges[k]?.timeS ?? 0;
    highTotal += fall - rise;
    lowTotal += nextRise - fall;
    cycles += 1;
    i = k;
  }
  if (cycles === 0) return null;
  const total = highTotal + lowTotal;
  return total > 0 ? highTotal / total : null;
}

function finiteSamples(series: LiveChannelSeries): Sample[] {
  const count = Math.min(series.time_s.length, series.voltage_v.length);
  const samples: Sample[] = [];
  for (let i = 0; i < count; i += 1) {
    const t = series.time_s[i];
    const v = series.voltage_v[i];
    if (t !== undefined && v !== undefined && Number.isFinite(t) && Number.isFinite(v)) {
      samples.push({ t, v });
    }
  }
  return samples;
}

// ── Форматтеры (точка как в остальном scope-табе; «—» для null) ──────────

export function formatVoltsValue(value: number): string {
  if (Math.abs(value) >= 1) return `${value.toFixed(3)} В`;
  return `${Math.round(value * 1000)} мВ`;
}

export function formatFrequencyValue(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(3)} МГц`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(3)} кГц`;
  return `${value.toFixed(1)} Гц`;
}

export function formatPeriodValue(value: number): string {
  if (value >= 1e-3) return `${(value * 1e3).toFixed(3)} мс`;
  if (value >= 1e-6) return `${(value * 1e6).toFixed(3)} мкс`;
  return `${(value * 1e9).toFixed(1)} нс`;
}

export function formatDutyValue(value: number): string {
  return `${(value * 100).toFixed(1)} %`;
}

export function formatMeasurement(value: number | null, format: (value: number) => string): string {
  return value === null ? "—" : format(value);
}
