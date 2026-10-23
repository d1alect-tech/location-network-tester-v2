/** Привязка preflight «Настроек» к живой форме захвата (U3 BIND).
 * Только чтение DOM: состояние формы захвата отсюда никогда не меняется.
 * Формы нет в документе, поля пусты или значения невалидны —
 * откат к DEFAULT_FORM_VALUES. Preflight всегда проверяет готовность
 * аппаратного захвата, поэтому запрос собирается с device-семантикой
 * (kind:"capture"), а режим даёт channels/input/self_noise/baseline. */

import type { CaptureJobRequest } from "../../api/types-jobs";
import {
  CAPTURE_MODES,
  DEFAULT_FORM_VALUES,
  buildJobRequest,
  validateCaptureForm,
} from "../../capture/modes";
import type {
  CaptureFormValues,
  CaptureModeDef,
  CaptureModeId,
  ValidatedCaptureForm,
} from "../../capture/modes";

const KNOWN_MODES: readonly string[] = [
  "rc_measurement",
  "self_noise",
  "line_quality",
  "single_channel",
  "ripple_measurement",
];

function isCaptureModeId(value: string): value is CaptureModeId {
  return KNOWN_MODES.includes(value);
}

/** Имя поля формы захвата → ключ значений (зеркало createModeForm). */
const FIELD_NAMES: Readonly<Record<keyof CaptureFormValues, string>> = {
  durationS: "duration_s",
  sampleRateHz: "sample_rate_hz",
  rangeV: "range_v",
  label: "label",
  baselineSession: "baseline_session",
  repeat: "repeat",
  intervalS: "interval_s",
  profile: "profile",
  adapterCapNf: "adapter_cap_nf",
  adapterSeriesROhm: "adapter_series_r_ohm",
  adapterPreconnected: "adapter_preconnected",
  adapterBasis: "adapter_component_values_basis",
};

function controlValue(form: HTMLFormElement, name: string): string {
  const control = form.elements.namedItem(name);
  if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement) {
    return control.value;
  }
  return "";
}

/** Декларация адаптера: галка читается как boolean, базис — с radio-пары
 * (RadioNodeList отдаёт значение отмеченной кнопки). */
function adapterOverrides(form: HTMLFormElement): Partial<CaptureFormValues> {
  const overrides: Partial<CaptureFormValues> = {};
  const checkbox = form.elements.namedItem(FIELD_NAMES.adapterPreconnected);
  if (checkbox instanceof HTMLInputElement && checkbox.type === "checkbox") {
    overrides.adapterPreconnected = checkbox.checked;
  }
  const basis = form.elements.namedItem(FIELD_NAMES.adapterBasis);
  if (basis instanceof RadioNodeList) {
    overrides.adapterBasis = basis.value === "operator_measured" ? "operator_measured" : "nominal";
  }
  return overrides;
}

function readMode(form: HTMLFormElement | null): CaptureModeDef {
  const checked = form?.querySelector<HTMLInputElement>('input[name="capture-mode"]:checked');
  const id = checked?.value ?? "";
  return isCaptureModeId(id) ? CAPTURE_MODES[id] : CAPTURE_MODES.rc_measurement;
}

/** Строковые поля формы — читаются value-чтением; галка и базис — ниже. */
const STRING_KEYS = [
  "durationS",
  "sampleRateHz",
  "rangeV",
  "label",
  "baselineSession",
  "repeat",
  "intervalS",
  "profile",
  "adapterCapNf",
  "adapterSeriesROhm",
] as const satisfies readonly (keyof CaptureFormValues)[];

function readRawValues(form: HTMLFormElement | null): CaptureFormValues {
  const values = { ...DEFAULT_FORM_VALUES };
  if (form === null) return values;
  for (const key of STRING_KEYS) {
    const raw = controlValue(form, FIELD_NAMES[key]);
    values[key] = raw.trim() === "" ? DEFAULT_FORM_VALUES[key] : raw;
  }
  return { ...values, ...adapterOverrides(form) };
}

function validatedOrDefault(values: CaptureFormValues): ValidatedCaptureForm {
  const { valid } = validateCaptureForm(values);
  if (valid !== null) return valid;
  const fallback = validateCaptureForm(DEFAULT_FORM_VALUES);
  if (fallback.valid === null) {
    throw new Error("DEFAULT_FORM_VALUES не проходит собственную валидацию");
  }
  return fallback.valid;
}

/** Собирает тело POST /api/capture/preflight из живой формы захвата.
 * Параметр root существует для тестов; в проде document по умолчанию. */
export function readCapturePreflightRequest(
  root: ParentNode = globalThis.document,
): CaptureJobRequest {
  const node = root.querySelector(".capture-form");
  const form = node instanceof HTMLFormElement ? node : null;
  const request = buildJobRequest(
    readMode(form),
    validatedOrDefault(readRawValues(form)),
    "device",
  );
  if (request.kind !== "capture") {
    throw new Error("preflight требует capture-запрос");
  }
  return request;
}
