/** Клиентский склад трасс SA (Todo 14): сервер трасс не хранит — вкладка
 * сама ведёт четыре трассы на общей сетке частот свипа. Clear-write
 * перезаписывается каждым свипом; min-hold/max-hold — поточечные
 * экстремумы (только падает/только растёт до clear); running-average —
 * бегущее среднее. Смена полосы меняет сетку: склад перечитывает её и
 * сеет статистику заново. Бюджет точек — паритет контракта
 * MAX_SPECTRUM_POINTS (5000 на трассу, models_live.py); вход за бюджет
 * или с мусорными значениями отклоняется, склад не трогается. */

export const SA_TRACE_POINT_BUDGET = 5_000;

export type SaTraceKind = "clear" | "max" | "min" | "avg";

interface Grid {
  freq: Float64Array;
  max: Float64Array;
  min: Float64Array;
  avg: Float64Array;
  clear: Float64Array;
  sweeps: number;
}

function isFiniteArray(values: readonly number[]): boolean {
  for (const value of values) {
    if (!Number.isFinite(value)) return false;
  }
  return true;
}

/** Точная сетка: прореживание детерминировано, одна полоса — одна сетка;
 * любое расхождение (в т.ч. при равной длине) — новая сетка, новый расчёт. */
function sameGrid(a: Float64Array, freq: readonly number[]): boolean {
  if (a.length !== freq.length) return false;
  for (let i = 0; i < freq.length; i += 1) {
    if (a[i] !== freq[i]) return false;
  }
  return true;
}

export class SaTraceStore {
  private grid: Grid | null = null;

  /** Один свип: false — вход отклонён (мусор/бюджет), склад нетронут. */
  applyTrace(freq: readonly number[], psdDb: readonly number[]): boolean {
    if (freq.length === 0 || freq.length !== psdDb.length) return false;
    if (freq.length > SA_TRACE_POINT_BUDGET) return false;
    if (!isFiniteArray(freq) || !isFiniteArray(psdDb)) return false;
    if (this.grid === null || !sameGrid(this.grid.freq, freq)) {
      this.seed(freq, psdDb);
      return true;
    }
    const grid = this.grid;
    grid.clear.set(psdDb);
    for (let i = 0; i < grid.freq.length; i += 1) {
      const value = psdDb[i] as number;
      const held = grid.max[i] as number;
      const kept = grid.min[i] as number;
      if (value > held) grid.max[i] = value;
      if (value < kept) grid.min[i] = value;
    }
    grid.sweeps += 1;
    const weight = 1 / grid.sweeps;
    for (let i = 0; i < grid.avg.length; i += 1) {
      const value = psdDb[i] as number;
      const mean = grid.avg[i] as number;
      grid.avg[i] = mean + (value - mean) * weight;
    }
    return true;
  }

  /** Сброс статистики: склад пуст, следующий свип сеет всё заново. */
  clear(): void {
    this.grid = null;
  }

  freq(): Float64Array | null {
    return this.grid === null ? null : this.grid.freq.slice();
  }

  /** Копия трассы; null — трассы нет (склад пуст). */
  trace(kind: SaTraceKind): Float64Array | null {
    return this.grid === null ? null : this.grid[kind].slice();
  }

  sweepCount(): number {
    return this.grid === null ? 0 : this.grid.sweeps;
  }

  private seed(freq: readonly number[], psdDb: readonly number[]): void {
    this.grid = {
      freq: Float64Array.from(freq),
      max: Float64Array.from(psdDb),
      min: Float64Array.from(psdDb),
      avg: Float64Array.from(psdDb),
      clear: Float64Array.from(psdDb),
      sweeps: 1,
    };
  }
}
