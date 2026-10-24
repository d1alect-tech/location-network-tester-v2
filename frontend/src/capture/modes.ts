/** Режимы захвата: ровно пять режимов из плана. Выбор режима определяет,
 * какие настройки существуют — невозможные комбинации не показываются.
 * Контракты зеркалируют CaptureRequest (src/lnt/ui/models.py). Валидация
 * вынесена в modesValidation.ts (N7-сплит под потолок 250 чистых LOC) и
 * реэкспортирована здесь — публичная поверхность не менялась. */

import type { CaptureJobRequest, SimulateJobRequest } from "../api/types-jobs";
import { ADAPTER_PRESET } from "./adapterPreset";
import { validateCaptureForm } from "./modesValidation";
import type { ValidatedCaptureForm } from "./modesValidation";

export { validateCaptureForm };
export type { ValidatedCaptureForm };

export const CAPTURE_MODE_IDS = [
  "rc_measurement",
  "self_noise",
  "line_quality",
  "single_channel",
  "ripple_measurement",
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
  ripple_measurement: {
    id: "ripple_measurement",
    titleRu: "Риппл-измерение (адаптер)",
    descriptionRu: `Тот же одноканальный CH1-поток, что и в одноканальном захвате, с зафиксированным пресетом адаптера (номинал ${ADAPTER_PRESET.capNfNominal} нФ / 1 МОм / x1). Декларация адаптера записывается в контекст сессии в момент захвата.`,
    channels: 1,
    input: "rc",
    selfNoise: false,
    usesBaseline: false,
    sessionTypeRu: "Измерение (measurement)",
    ch1SetupRu: "RC-развязка (floating differential RC shunt)",
  },
};

/** Значения формы как строки полей ввода (пустая строка = не задано);
 *  декларация адаптера — булево и литерал базиса, не строки. */
export interface CaptureFormValues {
  durationS: string;
  sampleRateHz: string;
  rangeV: string;
  label: string;
  baselineSession: string;
  repeat: string;
  intervalS: string;
  profile: string;
  adapterCapNf: string;
  adapterSeriesROhm: string;
  adapterPreconnected: boolean;
  adapterBasis: "nominal" | "operator_measured";
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
  // Пресет адаптера — импорт из N4, не хардкод чисел.
  adapterCapNf: String(ADAPTER_PRESET.capNfNominal),
  adapterSeriesROhm: String(ADAPTER_PRESET.seriesROhmNominal),
  // D4: утвердительная галка по умолчанию НЕ стоит.
  adapterPreconnected: false,
  adapterBasis: "nominal",
};

export type CaptureFieldErrors = Partial<Record<keyof CaptureFormValues, string>>;

/** Значения полей настроек/серии без декларации адаптера (владелец —
 *  modeFormFields; декларацию читает adapterDeclarationForm). */
export type CoreFormValues = Omit<
  CaptureFormValues,
  "adapterCapNf" | "adapterSeriesROhm" | "adapterPreconnected" | "adapterBasis"
>;

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
  // Декларация адаптера — только ripple-режим с осциллографом (D7);
  // прочие режимы и симулятор ключа не получают вовсе.
  const adapter =
    mode.id === "ripple_measurement"
      ? {
          adapter_declaration: {
            preconnected: form.adapterPreconnected,
            cap_nf: form.adapterCapNf,
            series_r_ohm: form.adapterSeriesROhm,
            component_values_basis: form.adapterBasis,
          },
        }
      : {};
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
    ...adapter,
  };
}
