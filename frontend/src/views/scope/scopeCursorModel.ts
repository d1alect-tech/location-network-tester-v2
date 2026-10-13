/** Модель курсоров осциллографа (выделена из scopeCursorSection, лимит
 * 250 чистых LOC): позиции T1/T2/V1/V2, дефолты, чистое вычисление строк
 * readout Δt/ΔV и окно времени канала. Форматирование —
 * scopeCursors/scopeMeasurements; DOM здесь нет. */

import type { LiveChannelSeries } from "../../api/types-live";
import {
  formatDeltaSecondsValue,
  formatDeltaVoltsValue,
  timeCursorDeltaSeconds,
  voltageCursorDeltaV,
} from "./scopeCursors";
import { formatPeriodValue, formatVoltsValue } from "./scopeMeasurements";

/** Позиции курсоров: T — доли окна [0..1], V — вольты номинальной шкалы. */
export interface CursorPositions {
  t1: number;
  t2: number;
  v1: number;
  v2: number;
}

/** Готовые строки readout для DOM-ячеек панели «Курсоры». */
export interface CursorReadout {
  readonly t1: string;
  readonly t2: string;
  readonly dt: string;
  readonly v1: string;
  readonly v2: string;
  readonly dv: string;
}

export const DEFAULT_T1 = 0.25;
export const DEFAULT_T2 = 0.75;
export const DEFAULT_V1 = -1;
export const DEFAULT_V2 = 1;

/** Показания курсоров: T — секунды окна (без окна «—»), V — вольты. */
export function cursorReadout(
  positions: CursorPositions,
  windowS: number | null,
  t0: number,
): CursorReadout {
  return {
    t1: windowS === null ? "—" : formatPeriodValue(t0 + positions.t1 * windowS),
    t2: windowS === null ? "—" : formatPeriodValue(t0 + positions.t2 * windowS),
    dt: formatDeltaSecondsValue(
      timeCursorDeltaSeconds({ t1: positions.t1, t2: positions.t2 }, windowS),
    ),
    v1: formatVoltsValue(positions.v1),
    v2: formatVoltsValue(positions.v2),
    dv: formatDeltaVoltsValue(voltageCursorDeltaV({ v1: positions.v1, v2: positions.v2 })),
  };
}

/** Окно времени канала: последний − первый отсчёт; пусто/вырождено — null. */
export function timeWindowS(series: LiveChannelSeries): number | null {
  const first = series.time_s[0];
  const last = series.time_s[series.time_s.length - 1];
  if (first === undefined || last === undefined) return null;
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
  const span = last - first;
  return span > 0 ? span : null;
}
