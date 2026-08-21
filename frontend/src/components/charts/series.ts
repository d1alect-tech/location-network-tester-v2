/** Преобразования рядов для uPlot-графиков панели (todo 41).
 * Мин/max-прореживание зеркалит семантику src/lnt/ui/decimation.py:
 * экстремумы и края ряда сохраняются всегда, иглы не теряются. */

export interface SeriesPairs {
  x: number[];
  y: number[];
}

const MIN_DECIMATION_POINTS = 4;

/** Глобальные конечные минимум и максимум ряда (null — нет конечных значений). */
export function globalExtremes(values: readonly number[]): { min: number; max: number } | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  let seen = false;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    seen = true;
    if (value < min) min = value;
    if (value > max) max = value;
  }
  return seen ? { min, max } : null;
}

/** Отбрасывает пары с нечисловыми координатами; порядок сохраняется. */
export function filterFinitePairs(x: readonly number[], y: readonly number[]): SeriesPairs {
  const count = Math.min(x.length, y.length);
  const outX: number[] = [];
  const outY: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const xi = x[i];
    const yi = y[i];
    if (xi === undefined || yi === undefined) continue;
    if (!Number.isFinite(xi) || !Number.isFinite(yi)) continue;
    outX.push(xi);
    outY.push(yi);
  }
  return { x: outX, y: outY };
}

/** Детерминированная очистка для логарифмических осей: обе координаты > 0. */
export function filterLogSafePairs(x: readonly number[], y: readonly number[]): SeriesPairs {
  const finite = filterFinitePairs(x, y);
  const outX: number[] = [];
  const outY: number[] = [];
  for (let i = 0; i < finite.x.length; i += 1) {
    const xi = finite.x[i];
    const yi = finite.y[i];
    if (xi === undefined || yi === undefined) continue;
    if (xi <= 0 || yi <= 0) continue;
    outX.push(xi);
    outY.push(yi);
  }
  return { x: outX, y: outY };
}

type Window = readonly (number | undefined)[];

function extremaIndices(window: Window, start: number): [number, number] {
  let minIdx = -1;
  let maxIdx = -1;
  let minValue = Number.POSITIVE_INFINITY;
  let maxValue = Number.NEGATIVE_INFINITY;
  window.forEach((value, i) => {
    if (value === undefined) return;
    if (value < minValue) {
      minValue = value;
      minIdx = i;
    }
    if (value >= maxValue) {
      maxValue = value;
      maxIdx = i;
    }
  });
  if (minIdx < 0 || maxIdx < 0) return [start, start];
  return minIdx <= maxIdx ? [start + minIdx, start + maxIdx] : [start + maxIdx, start + minIdx];
}

/** Min/max-огибающая: на ведро остаются и минимум, и максимум; края ряда
 * сохраняются; дубликаты индексов схлопываются. Порядок точек не меняется. */
export function decimateMinMax(
  x: readonly number[],
  y: readonly number[],
  maxPoints: number,
): SeriesPairs {
  if (maxPoints < MIN_DECIMATION_POINTS) {
    throw new Error("max_points должен быть не меньше 4");
  }
  const total = Math.min(x.length, y.length);
  if (total <= maxPoints) return { x: x.slice(0, total), y: y.slice(0, total) };

  const bucketCount = Math.floor((maxPoints - 2) / 2);
  const interiorCount = total - 2;
  const narrowWidth = Math.floor(interiorCount / bucketCount);
  const widerCount = interiorCount - narrowWidth * bucketCount;
  const widerWidth = narrowWidth + 1;
  const widerLength = widerCount * widerWidth;

  const indices: number[] = [0];
  const pushExtrema = (start: number, width: number): void => {
    const window: number[] = [];
    for (let i = 0; i < width; i += 1) {
      const value = y[start + i];
      if (value !== undefined) window.push(value);
    }
    for (const idx of extremaIndices(window, start)) indices.push(idx);
  };
  for (let b = 0; b < widerCount; b += 1) pushExtrema(1 + b * widerWidth, widerWidth);
  const narrowStart = 1 + widerLength;
  for (let b = 0; b < bucketCount - widerCount; b += 1) {
    pushExtrema(narrowStart + b * narrowWidth, narrowWidth);
  }
  indices.push(total - 1);

  const unique = indices.filter((idx, i) => i === 0 || idx !== indices[i - 1]);
  const outX: number[] = [];
  const outY: number[] = [];
  for (const idx of unique) {
    const xi = x[idx];
    const yi = y[idx];
    if (xi !== undefined && yi !== undefined) {
      outX.push(xi);
      outY.push(yi);
    }
  }
  return { x: outX, y: outY };
}

/** Уровень PSD в дБ: 10·lg(value). */
export function psdToDb(values: readonly number[]): number[] {
  return values.map((value) => 10 * Math.log10(value));
}

/** Амплитудная спектральная плотность из PSD: √PSD, В/√Гц. */
export function psdToAsd(psd: readonly number[]): number[] {
  return psd.map((value) => Math.sqrt(value));
}

/** CSV для доступной альтернативы графику: заголовок + строки. */
export function seriesToCsv(headers: string[], rows: ReadonlyArray<readonly number[]>): string {
  const lines = [headers.join(",")];
  for (const row of rows) lines.push(row.join(","));
  return `${lines.join("\n")}`;
}
