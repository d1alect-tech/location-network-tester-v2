/** Валидация формы захвата (N7-сплит modes.ts под потолок 250 чистых LOC):
 * русские по-полевые ошибки, диапазоны как в бэкенд-валидаторе, декларация
 * адаптера — C положительное, Rs неотрицательное, базис-литерал.
 * Публичная поверхность остаётся за modes.ts (реэкспорт). */

import type { CaptureFieldErrors, CaptureFormValues } from "./modes";

export interface ValidatedCaptureForm {
  durationS: number;
  sampleRateHz: number;
  rangeV: number;
  label: string | null;
  baselineSession: string | null;
  repeat: number;
  intervalS: number;
  profile: string;
  adapterCapNf: number;
  adapterSeriesROhm: number;
  adapterPreconnected: boolean;
  adapterBasis: "nominal" | "operator_measured";
}

const RANGE_VALUES = new Set([5, 1, 0.5]);
// Зеркало _validated_child_name: [A-Za-z0-9][A-Za-z0-9._-]{0,127}
const CHILD_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

function parsePositive(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw.replace(",", "."));
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}

function parseNonNegative(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw.replace(",", "."));
  if (!Number.isFinite(value) || value < 0) return null;
  return value;
}

/** Валидация до отправки: русские ошибки по полям; пустой объект — форма валидна. */
export function validateCaptureForm(values: CaptureFormValues): {
  valid: ValidatedCaptureForm | null;
  errors: CaptureFieldErrors;
} {
  const errors: CaptureFieldErrors = {};

  const durationS = parsePositive(values.durationS);
  if (durationS === null)
    errors.durationS = "Длительность должна быть положительным числом секунд.";

  const sampleRateHz = parsePositive(values.sampleRateHz);
  if (sampleRateHz === null) {
    errors.sampleRateHz = "Частота дискретизации должна быть положительным числом герц.";
  }

  const rangeV = parsePositive(values.rangeV);
  if (rangeV === null || !RANGE_VALUES.has(rangeV)) {
    errors.rangeV = "Диапазон должен быть одним из: 5, 1 или 0,5 В.";
  }

  const repeat = Number(values.repeat);
  if (!Number.isInteger(repeat) || repeat < 1) {
    errors.repeat = "Повторов должно быть целое число не меньше 1.";
  }

  const intervalS = parseNonNegative(values.intervalS);
  if (intervalS === null) {
    errors.intervalS = "Интервал стартов должен быть неотрицательным числом секунд.";
  }

  let baselineSession: string | null = null;
  const baselineRaw = values.baselineSession.trim();
  if (baselineRaw !== "" && !CHILD_NAME_PATTERN.test(baselineRaw)) {
    errors.baselineSession =
      "Имя базовой сессии: латиница, цифры и знаки . _ - , не длиннее 128 символов.";
  } else if (baselineRaw !== "") {
    baselineSession = baselineRaw;
  }

  const label = values.label.trim();
  if (label.length > 128) {
    errors.label = "Метка не длиннее 128 символов.";
  }

  // Декларация адаптера: C — положительное, Rs — неотрицательное, базис —
  // литерал (НИКОГДА не выводится из совпадения значений с номиналом).
  const adapterCapNf = parsePositive(values.adapterCapNf);
  if (adapterCapNf === null) {
    errors.adapterCapNf = "Ёмкость C должна быть положительным числом нанофарад.";
  }

  const adapterSeriesROhm = parseNonNegative(values.adapterSeriesROhm);
  if (adapterSeriesROhm === null) {
    errors.adapterSeriesROhm = "Последовательный R должен быть неотрицательным числом ом.";
  }

  if (values.adapterBasis !== "nominal" && values.adapterBasis !== "operator_measured") {
    errors.adapterBasis = "Базис значений должен быть «номинал» или «измерено оператором».";
  }

  if (Object.keys(errors).length > 0) return { valid: null, errors };
  return {
    valid: {
      durationS: durationS as number,
      sampleRateHz: sampleRateHz as number,
      rangeV: rangeV as number,
      label: label === "" ? null : label,
      baselineSession,
      repeat: repeat as number,
      intervalS: intervalS as number,
      profile: values.profile,
      adapterCapNf: adapterCapNf as number,
      adapterSeriesROhm: adapterSeriesROhm as number,
      adapterPreconnected: values.adapterPreconnected,
      adapterBasis: values.adapterBasis,
    },
    errors,
  };
}
