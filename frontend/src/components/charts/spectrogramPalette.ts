/** Палитра матрицы спектрограммы (todo 42): перцептивно упорядоченная шкала
 * из 9 ступеней, привязанная к токенам DESIGN.md §4.1/§4.5 (синий accent-a →
 * тёплый highlight). Порядок «темнее = меньше дБ» проверяется тестом на
 * монотонность относительной яркости; нецветовая альтернатива — числовая
 * шкала visualMap и выгрузка матрицы CSV. */

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
