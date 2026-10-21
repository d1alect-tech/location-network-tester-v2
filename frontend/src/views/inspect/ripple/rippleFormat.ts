/** Форматирование наблюдаемых величин и словарь причин панели ripple.
 * Только представление: ни одного пересчёта измерения. */

export const RIPPLE_DASH = "н/д";
const NBSP = "\u00A0";
export const SAMPLE_FORMAT = new Intl.NumberFormat("ru-RU");

const REASONS: Readonly<Record<string, string>> = {
  clipped: "клиппинг",
  clipping_unknown: "клиппинг не определён",
  nonfinite_samples: "нечисловые отсчёты",
  known_gap: "разрыв записи",
  settling_unknown: "установление не подтверждено",
  settling: "идёт окно установления",
  empty_span: "пустой интервал",
  insufficient_samples: "мало отсчётов",
  insufficient_segments: "мало сегментов спектра",
  baseline_incompatible: "фон несовместим",
  baseline_missing: "фон не приложен",
  baseline_calibration_identity_unknown: "калибровка фона неизвестна",
  stale_input: "входные файлы изменились",
};

function ruFixed(value: number, digits: number): string {
  return value.toFixed(digits).replace(".", ",");
}

function trim(value: number, digits: number): string {
  return value
    .toFixed(digits)
    .replace(/(\.\d*?)0+$/, "$1")
    .replace(/\.$/, "")
    .replace(".", ",");
}

/** Наблюдаемые вольты в ограниченном слоте: максимум 10–11 знаков,
 * запятая RU, неразрывный пробел перед единицей. null — только «н/д». */
export function formatVolts(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return RIPPLE_DASH;
  const abs = Math.abs(value);
  if (abs === 0) return `0,00${NBSP}мВ`;
  if (abs >= 0.9995) return `${ruFixed(value, 3)}${NBSP}В`;
  if (abs >= 0.0009995) return `${ruFixed(value * 1e3, 2)}${NBSP}мВ`;
  if (abs >= 0.0000009995) return `${ruFixed(value * 1e6, 2)}${NBSP}мкВ`;
  return `${ruFixed(value * 1e9, 2)}${NBSP}нВ`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return RIPPLE_DASH;
  if (seconds >= 1) return `${ruFixed(seconds, 3)}${NBSP}с`;
  if (seconds >= 0.001) return `${ruFixed(seconds * 1e3, 1)}${NBSP}мс`;
  return `${ruFixed(seconds * 1e6, 1)}${NBSP}мкс`;
}

export function formatHz(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${trim(value / 1e6, 2)}${NBSP}МГц`;
  if (abs >= 1e3) return `${trim(value / 1e3, 2)}${NBSP}кГц`;
  return `${trim(value, 1)}${NBSP}Гц`;
}

export function formatHzRange(low: number, high: number): string {
  const lowUnit = low >= 1e3 ? (formatHz(low).split(NBSP)[1] ?? "") : "Гц";
  const highText = formatHz(high);
  const highUnit = highText.split(NBSP)[1] ?? "";
  if (lowUnit !== highUnit) return `${formatHz(low)}–${highText}`;
  return `${trim(low >= 1e3 ? low / 1e3 : low, 2)}–${highText}`;
}

/** Машинный код причины: известный — по-русски, неизвестный — дословно. */
export function reasonText(code: string | null | undefined): string {
  if (code === null || code === undefined || code === "") return "причина не указана";
  return REASONS[code] ?? code;
}

export function reasonList(codes: readonly string[] | null | undefined): string {
  if (codes === null || codes === undefined || codes.length === 0) return "причина не указана";
  return [...new Set(codes.map((code) => reasonText(code)))].join(" · ");
}
