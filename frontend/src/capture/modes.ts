/** Режимы захвата: ровно четыре режима из плана. Выбор режима определяет,
 * какие настройки существуют — невозможные комбинации не показываются.
 * Контракты зеркалируют CaptureRequest (src/lnt/ui/models.py). */

import type { CaptureJobRequest, SimulateJobRequest } from "../api/types-jobs";

export const CAPTURE_MODE_IDS = [
  "rc_measurement",
  "self_noise",
  "line_quality",
  "single_channel",
] as const;
export type CaptureModeId = (typeof CAPTURE_MODE_IDS)[number];

export interface CaptureModeDef {
  id: CaptureModeId;
  titleRu: string;
  descriptionRu: string;
  /** Каналы фиксированы режимом: невозможные комбинации недостижимы. */
  channels: 1 | 2;
  input: "rc" | "transformer";
  selfNoise: boolean;
  /** Базовая сессия самошума применима только к режимам измерения. */
  usesBaseline: boolean;
  sessionTypeRu: string;
  ch1SetupRu: string;
}

export const CAPTURE_MODES: Record<CaptureModeId, CaptureModeDef> = {
  rc_measurement: {
    id: "rc_measurement",
    titleRu: "RC-измерение (двухканальное)",
    descriptionRu:
      "CH1 — ВЧ-фронтенд RC, CH2 — трансформатор 50 Гц для фазовой привязки. Все метрики доступны.",
    channels: 2,
    input: "rc",
    selfNoise: false,
    usesBaseline: true,
    sessionTypeRu: "Измерение (measurement)",
    ch1SetupRu: "RC-развязка (floating differential RC shunt)",
  },
  self_noise: {
    id: "self_noise",
    titleRu: "Терминированный самошум",
    descriptionRu:
      "Фронтенды отключены, входы терминированы 50 Ом: запись собственного шума прибора. Базовая сессия не применяется.",
    channels: 2,
    input: "rc",
    selfNoise: true,
    usesBaseline: false,
    sessionTypeRu: "Самошум (self_noise)",
    ch1SetupRu: "Терминированный вход 50 Ом",
  },
  line_quality: {
    id: "line_quality",
    titleRu: "Качество сети (трансформатор 230:6)",
    descriptionRu:
      "Один пробник на вторичке трансформатора 230:6, переключатель пробника в 10x (по умолчанию). Частота, RMS, THD и гармоники сети.",
    channels: 1,
    input: "transformer",
    selfNoise: false,
    usesBaseline: false,
    sessionTypeRu: "Качество сети (line_quality)",
    ch1SetupRu: "Трансформаторный пробник 230:6, множитель 10x",
  },
  single_channel: {
    id: "single_channel",
    titleRu: "Одноканальный захват",
    descriptionRu:
      "Только CH1 без привязки к фазе: спектр и пики считаются, метрики CH2 будут «н/д».",
    channels: 1,
    input: "rc",
    selfNoise: false,
    usesBaseline: true,
    sessionTypeRu: "Измерение (measurement)",
    ch1SetupRu: "RC-развязка (floating differential RC shunt)",
  },
};

/** Значения формы как строки полей ввода (пустая строка = не задано). */
export interface CaptureFormValues {
  durationS: string;
  sampleRateHz: string;
  rangeV: string;
  label: string;
  baselineSession: string;
  repeat: string;
  intervalS: string;
  profile: string;
}

export const DEFAULT_FORM_VALUES: CaptureFormValues = {
  durationS: "2.4",
  sampleRateHz: "8000000",
  rangeV: "5",
  label: "",
  baselineSession: "",
  repeat: "1",
  intervalS: "0",
  profile: "quiet",
};

export type CaptureFieldErrors = Partial<Record<keyof CaptureFormValues, string>>;

export interface ValidatedCaptureForm {
  durationS: number;
  sampleRateHz: number;
  rangeV: number;
  label: string | null;
  baselineSession: string | null;
  repeat: number;
  intervalS: number;
  profile: string;
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
    },
    errors,
  };
}

export type CaptureSource = "simulator" | "device";

/** Собирает запрос задачи строго по контракту бэкенда для выбранного режима.
 * Симулятор идёт через kind:"simulate", осциллограф — через kind:"capture". */
export function buildJobRequest(
  mode: CaptureModeDef,
  form: ValidatedCaptureForm,
  source: CaptureSource,
): SimulateJobRequest | CaptureJobRequest {
  const series = {
    label: form.label ?? undefined,
    repeat: form.repeat,
    interval_s: form.intervalS,
  };
  if (source === "simulator") {
    return {
      kind: "simulate",
      profile: form.profile,
      duration_s: form.durationS,
      sample_rate_hz: form.sampleRateHz,
      channels: mode.channels,
      ...series,
    };
  }
  return {
    kind: "capture",
    duration_s: form.durationS,
    sample_rate_hz: form.sampleRateHz,
    range_v: form.rangeV,
    self_noise: mode.selfNoise,
    baseline_session: mode.usesBaseline ? form.baselineSession : null,
    channels: mode.channels,
    input: mode.input,
    ...series,
  };
}
