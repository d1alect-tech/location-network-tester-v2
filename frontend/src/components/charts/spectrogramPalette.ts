/** Палитра матрицы спектрограммы (todo 42): перцептивно упорядоченная шкала
 * из 9 ступеней, привязанная к токенам DESIGN.md §4.1/§4.5 (синий accent-a →
 * тёплый highlight). Порядок «темнее = меньше дБ» проверяется тестом на
 * монотонность относительной яркости; нецветовая альтернатива — числовая
 * шкала visualMap и выгрузка матрицы CSV.
 *
 * Todo 5 (ui-refactor-2): ниже — также live-палитра грама (heat/delta):
 * значения скопированы байт-в-байт из замороженного
 * showcase-round2/spectrogramPalette.ts; захват импортирует их отсюда,
 * а не из витрины. Равенство копий пинится spectrogramPalette.test.ts. */

export const SPECTROGRAM_PALETTE = [
  "#1e3048",
  "#173a56",
  "#0f5f86",
  "#0f83a8",
  "#2aa7bd",
  "#4db9b4",
  "#7ccbb0",
  "#c9dc74",
  "#ffe066",
] as const;

export type SpectrogramPalette = typeof SPECTROGRAM_PALETTE;

/** Относительная яркость WCAG для hex-цвета (#rrggbb). */
export function relativeLuminance(hex: string): number {
  const value = Number.parseInt(hex.slice(1), 16);
  if (!Number.isFinite(value) || hex.length !== 7) return Number.NaN;
  const channel = (shift: number): number => {
    const raw = ((value >> shift) & 0xff) / 255;
    return raw <= 0.03928 ? raw / 12.92 : ((raw + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0);
}

/* ── Live-палитра грама: копия значений замороженного источника ────────────
 * (showcase-round2/spectrogramPalette.ts, только чтение). Блок скопирован
 * дословно; правки без before/after-скриншотов грама и без обновления
 * spectrogramPalette.test.ts запрещены. */

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
