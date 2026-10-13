/** 256-уровневое послесвечение осциллографа (Todo 11): аккумулятор
 * интенсивности W×H ячеек — Uint8, уровень 0..255 (256 уровней). Насыщающее
 * накопление попаданий (+HIT за точку, потолок 255) и целочисленное
 * затухание ×DECAY/256 за кадр (floor, след гарантированно гаснет до нуля).
 * Попадания кладутся и по сегментам между соседними точками — след копится
 * вдоль ЛИНИИ развёртки, а не в отдельных точках сэмпла. Бюджет памяти
 * фиксирован: 512×256×1 Б = 128 КиБ, роста нет. Затухание вызывается
 * ПЕРЕД pushChannel — свежий кадр светится полным уровнем. */

export const PERSISTENCE_GRID_W = 512;
export const PERSISTENCE_GRID_H = 256;
export const PERSISTENCE_HIT_LEVEL = 96;
/** Смягчение кромки следа: половина попадания в ячейки сверху/снизу. */
export const PERSISTENCE_SOFT_LEVEL = 48;
export const PERSISTENCE_DECAY_NUMERATOR = 220;
export const PERSISTENCE_MAX_LEVEL = 255;

export class ScopePersistence {
  private readonly cells = new Uint8Array(PERSISTENCE_GRID_W * PERSISTENCE_GRID_H);

  /** Кладёт канал кадра в аккумулятор: (t, v) → ячейка сетки; точки за
   * пределами диапазонов прижимаются к краю, неконечные пропускаются
   * (разрыв линии: сегмент через пропуск не проводится). */
  pushChannel(
    timeS: readonly number[],
    voltageV: readonly number[],
    vMin: number,
    vMax: number,
  ): void {
    if (timeS.length === 0 || timeS.length !== voltageV.length) return;
    const tMin = timeS[0] as number;
    const tSpan = (timeS[timeS.length - 1] as number) - tMin;
    const vSpan = vMax - vMin;
    let prevX = -1;
    let prevY = -1;
    for (let i = 0; i < timeS.length; i += 1) {
      const t = timeS[i] as number;
      const v = voltageV[i] as number;
      if (!Number.isFinite(t) || !Number.isFinite(v)) {
        prevX = -1;
        continue;
      }
      const x = tSpan > 0 ? clampCell((t - tMin) / tSpan, PERSISTENCE_GRID_W) : 0;
      const y =
        vSpan > 0 ? clampCell(1 - (v - vMin) / vSpan, PERSISTENCE_GRID_H) : PERSISTENCE_GRID_H >> 1;
      this.hit(x, y);
      if (prevX >= 0) this.hitSegment(prevX, prevY, x, y);
      prevX = x;
      prevY = y;
    }
  }

  /** Шаг затухания: level → level × 220 / 256 (целочисленный пол). */
  decay(): void {
    const cells = this.cells;
    for (let i = 0; i < cells.length; i += 1) {
      cells[i] = ((cells[i] as number) * PERSISTENCE_DECAY_NUMERATOR) >> 8;
    }
  }

  levelAt(x: number, y: number): number {
    if (x < 0 || x >= PERSISTENCE_GRID_W || y < 0 || y >= PERSISTENCE_GRID_H) return 0;
    return this.cells[y * PERSISTENCE_GRID_W + x] as number;
  }

  /** Число светящихся ячеек (уровень > 0) — для тестов и диагностики. */
  litCells(): number {
    let lit = 0;
    for (let i = 0; i < this.cells.length; i += 1) {
      if ((this.cells[i] as number) > 0) lit += 1;
    }
    return lit;
  }

  clear(): void {
    this.cells.fill(0);
  }

  private hit(x: number, y: number): void {
    const cells = this.cells;
    const cell = y * PERSISTENCE_GRID_W + x;
    const level = (cells[cell] as number) + PERSISTENCE_HIT_LEVEL;
    cells[cell] = level > PERSISTENCE_MAX_LEVEL ? PERSISTENCE_MAX_LEVEL : level;
    if (y > 0) this.soften(cell - PERSISTENCE_GRID_W);
    if (y < PERSISTENCE_GRID_H - 1) this.soften(cell + PERSISTENCE_GRID_W);
  }

  private soften(cell: number): void {
    const level = (this.cells[cell] as number) + PERSISTENCE_SOFT_LEVEL;
    this.cells[cell] = level > PERSISTENCE_MAX_LEVEL ? PERSISTENCE_MAX_LEVEL : level;
  }

  /** Линия между соседними точками кадра: ячейки вдоль отрезка, как луч ЭЛТ. */
  private hitSegment(x0: number, y0: number, x1: number, y1: number): void {
    const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0));
    for (let s = 1; s < steps; s += 1) {
      const share = s / steps;
      const x = Math.round(x0 + (x1 - x0) * share);
      const y = Math.round(y0 + (y1 - y0) * share);
      this.hit(x, y);
    }
  }
}

function clampCell(fraction: number, size: number): number {
  const cell = Math.floor(fraction * size);
  if (cell < 0) return 0;
  if (cell > size - 1) return size - 1;
  return cell;
}
