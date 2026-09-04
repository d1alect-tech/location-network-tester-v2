/** C3: display-only единицы спектра рядом с дБВ/Гц. Хранимый формат неизменен:
 * spectrum.csv остаётся в В²/Гц, тоггл сдвигает только отображаемые уровни.
 * Дельты A−B в дБ от единицы не зависят. */

import { el, nextId } from "../../components/primitives/dom";

export type SpectrumDisplayUnit = "dbv" | "dbuv" | "dbm50";

export const SPECTRUM_UNIT_OPTIONS: readonly { value: SpectrumDisplayUnit; label: string }[] = [
  { value: "dbv", label: "дБВ/Гц" },
  { value: "dbuv", label: "дБмкВ/Гц" },
  { value: "dbm50", label: "дБм/Гц · 50 Ом" },
];

/** Сдвиг отображаемого уровня относительно дБ (отн. 1 В²/Гц). */
export const UNIT_OFFSET_DB: Record<SpectrumDisplayUnit, number> = {
  dbv: 0,
  dbuv: 120,
  dbm50: 10 * Math.log10(20),
};

export const UNIT_REF_LABELS: Record<SpectrumDisplayUnit, string> = {
  dbv: "дБ (отн. 1 В²/Гц)",
  dbuv: "дБ (отн. 1 мкВ²/Гц)",
  dbm50: "дБм (50 Ом, отн. 1 мВт)",
};

/** Сдвигает готовый дБ-уровень под единицу отображения; NaN/±∞ — как есть. */
export function shiftLevelDb(levelDb: number, unit: SpectrumDisplayUnit): number {
  if (!Number.isFinite(levelDb)) return levelDb;
  return levelDb + UNIT_OFFSET_DB[unit];
}

export function unitRefLabel(unit: SpectrumDisplayUnit): string {
  return UNIT_REF_LABELS[unit];
}

export function parseDisplayUnit(value: string): SpectrumDisplayUnit | null {
  return value === "dbv" || value === "dbuv" || value === "dbm50" ? value : null;
}

export interface UnitsControl {
  readonly root: HTMLElement;
  unit(): SpectrumDisplayUnit;
}

const UNIT_STORAGE_KEY = "lnt.spectrum.unit";

/** Тоггл единиц отображения; выбор переживает перезагрузку, данные не трогает. */
export function createUnitsControl(onChange: () => void): UnitsControl {
  const selectId = nextId("spectrum-unit");
  const select = el("select", { attrs: { id: selectId, "data-spectrum-unit-select": "" } });
  for (const option of SPECTRUM_UNIT_OPTIONS) {
    select.append(el("option", { text: option.label, attrs: { value: option.value } }));
  }
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(UNIT_STORAGE_KEY);
  } catch {
    stored = null;
  }
  if (parseDisplayUnit(stored ?? "") !== null) select.value = stored as SpectrumDisplayUnit;
  select.addEventListener("change", () => {
    try {
      window.localStorage.setItem(UNIT_STORAGE_KEY, select.value);
    } catch {
      /* приватный режим: выбор живёт до перезагрузки */
    }
    onChange();
  });
  const root = el("div", { className: "spectrum-units", attrs: { "data-spectrum-units": "" } }, [
    el("label", { text: "Единицы", attrs: { for: selectId } }, [select]),
  ]);
  return {
    root,
    unit() {
      return parseDisplayUnit(select.value) ?? "dbv";
    },
  };
}
