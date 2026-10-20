/** Единицы отображения трасс SA (Todo 14): склад хранит дБ (проводной
 * формат 10·log10 PSD В²/Гц), тоггл меняет только отображение — как
 * spectrumUnits.ts инспекции (C3): хранимый формат не трогается.
 * Обратный перевод в линейную плотность амплитуды: √PSD = 10^(дБ/20). */

export type SaDisplayUnit = "dbv" | "v";

export const SA_UNIT_OPTIONS: readonly { value: SaDisplayUnit; label: string }[] = [
  { value: "dbv", label: "дБВ/Гц" },
  { value: "v", label: "В/√Гц" },
];

export function parseSaUnit(value: string): SaDisplayUnit | null {
  return value === "dbv" || value === "v" ? value : null;
}

/** Переводит дБ-уровень провода в отображаемое значение единицы. */
export function saLevelToDisplay(levelDb: number, unit: SaDisplayUnit): number {
  if (!Number.isFinite(levelDb)) return levelDb;
  return unit === "dbv" ? levelDb : 10 ** (levelDb / 20);
}

/** Подпись оси Y под выбранную единицу. */
export function saYAxisLabel(unit: SaDisplayUnit): string {
  return unit === "dbv" ? "Уровень, дБ" : "Уровень, В/√Гц";
}

/** Подпись деления оси X: короткий формат «250 кГц» / «4 МГц» — полный
 *  «4,000,000» при шаге uPlot 50 px слипается соседними подписями. */
export function formatFrequencyTick(value: number): string {
  if (!Number.isFinite(value)) return "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${trimTick(value / 1_000_000)} МГц`;
  if (abs >= 1_000) return `${trimTick(value / 1_000)} кГц`;
  return `${Math.round(value)} Гц`;
}

function trimTick(value: number): string {
  return Number(value.toFixed(2)).toString().replace(".", ",");
}

/** Частота для таблиц и показаний: кГц/МГц с одной десятой. */
export function formatHz(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} МГц`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} кГц`;
  return `${Math.round(value)} Гц`;
}

/** Уровень/превышение в дБ — одна десятая; мусор остаётся прочерком. */
export function formatDb(value: number): string {
  return Number.isFinite(value) ? value.toFixed(1) : "—";
}
