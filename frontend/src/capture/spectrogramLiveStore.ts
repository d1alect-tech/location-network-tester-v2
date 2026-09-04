/** Кольцевой склад колонок live-спектрограммы: Float32Array TIME_BINS × FREQ_BINS.
 * Ресемплинг спектра в лог-бины, дБ-значения, диапазон частот, статистика кадра. */

export type LiveGramMode = "a" | "b" | "delta";

/** Столбцов времени в кольце (как TIME_BINS витрины). */
export const TIME_BINS = 48;
/** Лог-бинов частоты на колонку (ресемплинг спектра). */
export const FREQ_BINS = 256;
/** Пол для неположительной мощности, дБ. */
export const LIVE_FLOOR_DB = -120;

function nearestIndex(sorted: readonly number[], value: number): number {
  let low = 0;
  let high = sorted.length - 1;
  while (high - low > 1) {
    const mid = (low + high) >> 1;
    if ((sorted[mid] as number) < value) low = mid;
    else high = mid;
  }
  const a = sorted[low] as number;
  const b = sorted[high] as number;
  return Math.abs(a - value) <= Math.abs(b - value) ? low : high;
}

export class LiveGramStore {
  private readonly cells = new Float32Array(TIME_BINS * FREQ_BINS).fill(LIVE_FLOOR_DB);
  private head = 0;
  private count = 0;
  private logMin = Math.log10(1000);
  private logMax = Math.log10(10_000_000);

  columnCount(): number {
    return this.count;
  }

  freqDomain(): { minHz: number; maxHz: number } {
    return { minHz: 10 ** this.logMin, maxHz: 10 ** this.logMax };
  }

  setFreqDomain(minHz: number, maxHz: number): boolean {
    if (!(minHz > 0) || !(maxHz > minHz)) return false;
    this.logMin = Math.log10(minHz);
    this.logMax = Math.log10(maxHz);
    return true;
  }

  binCenter(bin: number): number {
    return 10 ** (this.logMin + ((bin + 0.5) / FREQ_BINS) * (this.logMax - this.logMin));
  }

  /** Физическая строка k-й по возрасту колонки (0 — старейшая). */
  rowPhysical(k: number): number {
    return (this.head - this.count + k + TIME_BINS * 2) % TIME_BINS;
  }

  cellAt(row: number, bin: number): number {
    return this.cells[row * FREQ_BINS + bin] as number;
  }

  /** Значение полотна в дБ: уровень либо отклонение от среднего столбца. */
  valueAt(bin: number, row: number, mode: LiveGramMode): number {
    const value = this.cellAt(row, bin);
    if (mode !== "delta") return value;
    let mean = 0;
    for (let b = 0; b < FREQ_BINS; b += 1) mean += this.cellAt(row, b);
    return value - mean / FREQ_BINS;
  }

  levelRange(): { low: number; high: number } {
    let low = Number.POSITIVE_INFINITY;
    let high = Number.NEGATIVE_INFINITY;
    for (let k = 0; k < this.count; k += 1) {
      const row = this.rowPhysical(k);
      for (let b = 0; b < FREQ_BINS; b += 1) {
        const value = this.cellAt(row, b);
        if (value < low) low = value;
        if (value > high) high = value;
      }
    }
    return Number.isFinite(low) ? { low, high } : { low: -90, high: -30 };
  }

  /** Кладёт колонку в кольцо; false — пустой вход, кольцо не тронуто.
   * Пик-детектор: в бин пишется MAX сэмплов (в дБ max корректен как max PSD),
   * пустые бины — nearest как раньше. */
  pushSpectrumColumn(frequencyHz: readonly number[], psdDb: readonly number[]): boolean {
    if (frequencyHz.length < 2 || frequencyHz.length !== psdDb.length) return false;
    const span = this.logMax - this.logMin;
    const peak = new Float32Array(FREQ_BINS).fill(Number.NEGATIVE_INFINITY);
    for (let i = 0; i < frequencyHz.length; i += 1) {
      const freq = frequencyHz[i] as number;
      if (!(freq > 0) || span <= 0) continue;
      const t = (Math.log10(freq) - this.logMin) / span;
      if (!(t >= 0 && t < 1)) continue;
      const bin = Math.min(FREQ_BINS - 1, Math.floor(t * FREQ_BINS));
      const value = psdDb[i] as number;
      if (value > (peak[bin] ?? Number.NEGATIVE_INFINITY)) peak[bin] = value;
    }
    for (let bin = 0; bin < FREQ_BINS; bin += 1) {
      const max = peak[bin] as number;
      this.cells[this.head * FREQ_BINS + bin] = Number.isFinite(max)
        ? max
        : (psdDb[nearestIndex(frequencyHz, this.binCenter(bin))] as number);
    }
    this.head = (this.head + 1) % TIME_BINS;
    this.count = Math.min(this.count + 1, TIME_BINS);
    return true;
  }
}
