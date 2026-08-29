/** Цветовые шкалы спектрограммы V6.
 *
 *  Две разные по смыслу: уровень — последовательная шкала, дельта — расходящаяся,
 *  причём в цветах самих трасс графика (§4), чтобы «синий» и «оранжевый» на полотне
 *  читались тем же словарём, что и линии спектра и чипы ролей в каталоге. */

/** Половина ширины шкалы дельты в дБ: за пределами цвет насыщается. */
export const DELTA_SPAN_DB = 8;

export type Rgb = readonly [number, number, number];

export function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/** Уровень: тёмно-синий → бирюзовый → песочный. */
export function heatColor(unit: number): Rgb {
  const t = clamp01(unit);
  if (t < 0.5) {
    const k = t * 2;
    return [Math.round(18 + 12 * k), Math.round(26 + 96 * k), Math.round(54 + 78 * k)];
  }
  const k = (t - 0.5) * 2;
  return [Math.round(30 + 200 * k), Math.round(122 + 78 * k), Math.round(132 - 42 * k)];
}

/** Дельта: синий — сравнение тише базы, оранжевый — громче, фон — совпадение. */
export function deltaColor(db: number): Rgb {
  const t = clamp01(Math.abs(db) / DELTA_SPAN_DB);
  const base: Rgb = db < 0 ? [86, 129, 255] : [230, 134, 25];
  return [
    Math.round(29 + (base[0] - 29) * t),
    Math.round(29 + (base[1] - 29) * t),
    Math.round(29 + (base[2] - 29) * t),
  ];
}
