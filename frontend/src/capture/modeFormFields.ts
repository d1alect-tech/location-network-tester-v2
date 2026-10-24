/** Поля формы захвата: контролы, V6-обёртки .field/.field-label, карта ошибок
 * и чтение значений. Вынесено из modeForm.ts без изменения разметки — классы,
 * name=-атрибуты, подсказки и порядок создания узлов сохранены (пины
 * capture.spec.ts / captureV6.test.ts и счётчик nextId не должны дрейфовать). */

import { el } from "../components/primitives/dom";
import { type FieldHandle, createField } from "../components/primitives/forms";
import { DEFAULT_FORM_VALUES } from "./modes";
import type { CaptureFieldErrors, CoreFormValues } from "./modes";

function numberInput(name: string, step = "any", min?: string): HTMLInputElement {
  const input = el("input", {
    className: "lnt-input ctl",
    attrs: { type: "number", name, step, inputmode: "decimal" },
  });
  if (min !== undefined) input.setAttribute("min", min);
  return input;
}

/** V6-обёртка поля: дуал-класс .field/.field-label поверх lnt-примитива.
 *  Старые lnt-* классы остаются для e2e-пинов capture.spec.ts. */
export function v6field<T extends { root: HTMLElement }>(field: T): T {
  field.root.classList.add("field");
  field.root.querySelector("label")?.classList.add("field-label");
  return field;
}

/** V6 radio-card (D1=A): новый карточный класс ПОВЕРХ существующей разметки.
 *  input[name] + label[for] + value/checked не меняются — селекторы пинятся. */
export function radioCard(
  radio: HTMLInputElement,
  titleText: string,
  descText: string,
): HTMLLabelElement {
  const title = el("span", { className: "capture-mode-title radio-card-title", text: titleText });
  const desc = el("span", { className: "capture-mode-desc radio-card-desc", text: descText });
  const label = el("label", { className: "capture-mode-card radio-card" }, [radio, title, desc]);
  label.htmlFor = radio.id;
  return label;
}

export interface ModeFormFields {
  /** Строка «Каналы: …» — текст зависит от выбранного режима. */
  readonly channelsText: HTMLElement;
  /** Обёртка поля базовой сессии — скрывается у режимов без базы. */
  readonly baselineWrap: HTMLElement;
  /** Корень поля профиля симуляции — скрывается у источника «осциллограф». */
  readonly profileFieldRoot: HTMLElement;
  readonly repeatField: FieldHandle;
  readonly intervalField: FieldHandle;
  readonly profileField: FieldHandle;
  /** Сетка всегда видимых настроек; порядок узлов тот же, что до сплита. */
  readonly settingsFields: HTMLElement;
  values(): CoreFormValues;
  setErrors(errors: CaptureFieldErrors): void;
  clearErrors(): void;
}

export function createModeFormFields(): ModeFormFields {
  // --- Всегда видимые критичные настройки ---
  const durationInput = numberInput("duration_s", "0.1", "0.01");
  durationInput.value = DEFAULT_FORM_VALUES.durationS;
  const rateInput = numberInput("sample_rate_hz", "any", "1");
  rateInput.value = DEFAULT_FORM_VALUES.sampleRateHz;
  const rangeSelect = el("select", { className: "lnt-select ctl", attrs: { name: "range_v" } }, [
    el("option", { text: "5 В", attrs: { value: "5" } }),
    el("option", { text: "1 В", attrs: { value: "1" } }),
    el("option", { text: "0,5 В", attrs: { value: "0.5" } }),
  ]) as HTMLSelectElement;
  rangeSelect.value = DEFAULT_FORM_VALUES.rangeV;
  const labelInput = el("input", {
    className: "lnt-input ctl",
    attrs: { type: "text", name: "label", maxlength: "128" },
  }) as HTMLInputElement;

  const durationField = v6field(createField({ label: "Длительность, с", control: durationInput }));
  const rateField = v6field(
    createField({
      label: "Частота дискретизации, Гц",
      control: rateInput,
      hintText: "АЦП осциллографа: до 8–24 МГц; симулятор допускает любые значения.",
    }),
  );
  const rangeField = v6field(createField({ label: "Диапазон CH1", control: rangeSelect }));
  const labelField = v6field(createField({ label: "Метка", control: labelInput }));

  // Строка проекции каналов: текст зависит от режима (см. modeFormVisibility).
  const channelsText = el("p", {
    className: "capture-channels-value glyph glyph-ok",
    text: "Каналы: 2 (CH1 + CH2)",
  });

  // --- Базовая сессия (видима только у режимов, которые её используют) ---
  const baselineInput = el("input", {
    className: "lnt-input ctl",
    attrs: { type: "text", name: "baseline_session" },
  }) as HTMLInputElement;
  const baselineField = v6field(
    createField({
      label: "Базовая сессия (самошум)",
      control: baselineInput,
      hintText:
        "Имя записанной сессии самошума этой локации; спектр CH1 будет приведён ко входу. Оставьте пустым, если база не нужна.",
    }),
  );
  const baselineWrap = el("div", {}, [baselineField.root]);

  // --- Необязательные разделы за раскрытием ---
  const repeatInput = numberInput("repeat", "1", "1");
  repeatInput.value = DEFAULT_FORM_VALUES.repeat;
  const intervalInput = numberInput("interval_s", "0.1", "0");
  intervalInput.value = DEFAULT_FORM_VALUES.intervalS;
  const profileSelect = el("select", {
    className: "lnt-select ctl",
    attrs: { name: "profile" },
  }) as HTMLSelectElement;
  for (const profile of ["bad", "bad-damped", "quiet", "sync-only", "async-heavy"]) {
    profileSelect.append(el("option", { text: profile, attrs: { value: profile } }));
  }
  profileSelect.value = DEFAULT_FORM_VALUES.profile;

  const repeatField = v6field(
    createField({
      label: "Повторов, шт.",
      control: repeatInput,
      hintText: "Серия повторных записей; каждая сессия пишется отдельно.",
    }),
  );
  const intervalField = v6field(
    createField({ label: "Интервал стартов, с", control: intervalInput }),
  );
  const profileField = v6field(createField({ label: "Профиль симуляции", control: profileSelect }));

  const settingsFields = el("div", { className: "capture-settings-grid form-grid" }, [
    durationField.root,
    rateField.root,
    rangeField.root,
    channelsText,
    baselineWrap,
    labelField.root,
  ]);

  const fieldByErrorKey: Record<string, { setError(message: string | null): void }> = {
    durationS: durationField,
    sampleRateHz: rateField,
    rangeV: rangeField,
    label: labelField,
    baselineSession: baselineField,
    repeat: repeatField,
    intervalS: intervalField,
  };

  return {
    channelsText,
    baselineWrap,
    profileFieldRoot: profileField.root,
    repeatField,
    intervalField,
    profileField,
    settingsFields,
    values: (): CoreFormValues => ({
      durationS: durationInput.value,
      sampleRateHz: rateInput.value,
      rangeV: rangeSelect.value,
      label: labelInput.value,
      baselineSession: baselineInput.value,
      repeat: repeatInput.value,
      intervalS: intervalInput.value,
      profile: profileSelect.value,
    }),
    setErrors: (errors: CaptureFieldErrors): void => {
      for (const [key, field] of Object.entries(fieldByErrorKey)) {
        field.setError(errors[key as keyof CaptureFieldErrors] ?? null);
      }
    },
    clearErrors: (): void => {
      for (const field of Object.values(fieldByErrorKey)) field.setError(null);
    },
  };
}
