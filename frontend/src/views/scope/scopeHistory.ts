/** Кольцевая история кадров осциллографа (Todo 11): последние N кадров
 * с прокруткой назад. Бюджет памяти фиксирован и задокументирован:
 * HISTORY_FRAMES (N = 120 кадров) × 4 массива Float32 × HISTORY_POINT_CAP
 * (4000 точек — прореживание бэкенда ≤4000 display-точек) × 4 Б = 64 КиБ
 * на кадр, 7 680 000 Б (≈7,3 МиБ) потолок. Кадр длиннее кэпа прореживается
 * шагом ceil(len/cap); данные копируются в ограниченные Float32Array —
 * мутация источника и рост RAM исключены, только ограниченные массивы. */

import type { LiveChannelSeries, LiveFramePayload } from "../../api/types-live";

export const HISTORY_FRAMES = 120;
export const HISTORY_POINT_CAP = 4000;

export interface ScopeHistorySeries {
  readonly timeS: Float32Array;
  readonly voltageV: Float32Array;
}

export interface ScopeHistoryFrame {
  readonly frameIndex: number;
  readonly triggered: boolean;
  readonly emittedAtS: number;
  readonly ch1: ScopeHistorySeries;
  readonly ch2: ScopeHistorySeries;
}

/** Копия с прореживанием: длина выхода ≤ HISTORY_POINT_CAP, шаг ≥ 1. */
function boundedCopy(source: readonly number[]): Float32Array {
  const stride =
    source.length <= HISTORY_POINT_CAP ? 1 : Math.ceil(source.length / HISTORY_POINT_CAP);
  const length = Math.ceil(source.length / stride);
  const out = new Float32Array(length);
  for (let i = 0, j = 0; j < length; i += stride, j += 1) out[j] = source[i] as number;
  return out;
}

function seriesOf(series: LiveChannelSeries): ScopeHistorySeries {
  return { timeS: boundedCopy(series.time_s), voltageV: boundedCopy(series.voltage_v) };
}

export class ScopeHistory {
  private readonly slots: Array<ScopeHistoryFrame | null> = Array.from(
    { length: HISTORY_FRAMES },
    () => null,
  );
  private head = 0;
  private count = 0;

  /** Кладёт кадр в кольцо: копия данных, старейший вытесняется при N+1. */
  push(frame: LiveFramePayload): void {
    const stored: ScopeHistoryFrame = {
      frameIndex: frame.frame_index,
      triggered: frame.triggered,
      emittedAtS: frame.emitted_at_s,
      ch1: seriesOf(frame.ch1),
      ch2: seriesOf(frame.ch2),
    };
    this.slots[this.head] = stored;
    this.head = (this.head + 1) % HISTORY_FRAMES;
    this.count = Math.min(this.count + 1, HISTORY_FRAMES);
  }

  frameCount(): number {
    return this.count;
  }

  /** Кадр offset шагов назад: 0 — новейший (живой); null — вне кольца. */
  view(offset: number): ScopeHistoryFrame | null {
    if (this.count === 0 || offset < 0 || offset >= this.count) return null;
    const physical = (this.head - 1 - offset + HISTORY_FRAMES * 2) % HISTORY_FRAMES;
    return this.slots[physical] ?? null;
  }

  clear(): void {
    this.slots.fill(null);
    this.head = 0;
    this.count = 0;
  }

  /** Фактические байты буфера — для бюджет-теста. */
  usedBytes(): number {
    let bytes = 0;
    for (const slot of this.slots) {
      if (slot === null) continue;
      bytes +=
        slot.ch1.timeS.byteLength +
        slot.ch1.voltageV.byteLength +
        slot.ch2.timeS.byteLength +
        slot.ch2.voltageV.byteLength;
    }
    return bytes;
  }

  /** Потолок бюджета: N × 4 массива × кэп × 4 Б. */
  byteBudget(): number {
    return HISTORY_FRAMES * 4 * HISTORY_POINT_CAP * 4;
  }
}
