/** Модель курсоров осциллографа (Todo 10): чистые функции без DOM.
 * Курсоры времени — доли окна кадра [0..1] (окно знает только applyFrame);
 * курсоры напряжения — вольты в номинальной шкале CH1 ±5 В из дефолтного
 * запроса запуска. Readout Δt/ΔV — паттерн spectrumReadout: чистая
 * функция, null на отсутствии данных, «—» в UI. */

import { formatPeriodValue, formatVoltsValue } from "./scopeMeasurements";

/** Номинальная шкала курсоров напряжения: дефолт ch1_range_v запуска. */
export const VOLT_CURSOR_SPAN_V = 5;

/** Зажим доли окна кадра в [0..1]. */
export function clampFraction(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** Δt курсоров времени: |t2 − t1| · окно кадра; нет окна — null. */
export function timeCursorDeltaSeconds(
  positions: { t1: number; t2: number },
  windowS: number | null,
): number | null {
  if (windowS === null || !Number.isFinite(windowS) || windowS <= 0) return null;
  return Math.abs(positions.t2 - positions.t1) * windowS;
}

/** ΔV курсоров напряжения: |v2 − v1| в номинальной шкале. */
export function voltageCursorDeltaV(positions: { v1: number; v2: number }): number {
  return Math.abs(positions.v2 - positions.v1);
}

export function formatDeltaSecondsValue(value: number | null): string {
  return value === null ? "—" : formatPeriodValue(value);
}

export function formatDeltaVoltsValue(value: number | null): string {
  return value === null ? "—" : formatVoltsValue(value);
}
