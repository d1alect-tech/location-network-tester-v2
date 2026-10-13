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
