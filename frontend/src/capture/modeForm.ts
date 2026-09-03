/** Форма режима захвата: mode-first выбор из четырёх режимов, всегда видимые
 * критичные настройки, необязательные разделы за раскрытием. Базовая сессия
 * видима у всех режимов, которые её используют; невозможные поля не показываются. */

import { el } from "../components/primitives/dom";
import { createField } from "../components/primitives/forms";
import { createDisclosure } from "./disclosure";
import { CAPTURE_MODES, CAPTURE_MODE_IDS, DEFAULT_FORM_VALUES } from "./modes";
import type {
  CaptureFieldErrors,
  CaptureFormValues,
  CaptureModeDef,
  CaptureModeId,
  CaptureSource,
} from "./modes";

export interface ModeFormHandle {
  root: HTMLFormElement;
  getMode(): CaptureModeDef;
  getSource(): CaptureSource;
  values(): CaptureFormValues;
  setErrors(errors: CaptureFieldErrors): void;
  clearErrors(): void;
  /** Подписка на любое изменение режима/источника/полей (перерисовка превью). */
  onChange(listener: () => void): void;
  focusFirstInvalid(): void;
}

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
function v6field<T extends { root: HTMLElement }>(field: T): T {
  field.root.classList.add("field");
  field.root.querySelector("label")?.classList.add("field-label");
  return field;
}

/** V6 radio-card (D1=A): новый карточный класс ПОВЕРХ существующей разметки.
 *  input[name] + label[for] + value/checked не меняются — селекторы пинятся. */
function radioCard(radio: HTMLInputElement, titleText: string, descText: string): HTMLLabelElement {
  const title = el("span", { className: "capture-mode-title radio-card-title", text: titleText });
  const desc = el("span", { className: "capture-mode-desc radio-card-desc", text: descText });
  const label = el("label", { className: "capture-mode-card radio-card" }, [radio, title, desc]);
  label.htmlFor = radio.id;
  return label;
}

export function createModeForm(): ModeFormHandle {
  const listeners = new Set<() => void>();
  const notify = (): void => {
    for (const listener of listeners) listener();
  };

  // --- Режим измерения (mode-first) ---
  const modeRadios = new Map<CaptureModeId, HTMLInputElement>();
  const modeFieldset = el("fieldset", { className: "capture-mode-group" }, [
    el("legend", { text: "Режим измерения" }),
  ]);
  for (const id of CAPTURE_MODE_IDS) {
    const def = CAPTURE_MODES[id];
    const radio = el("input", {
      className: "capture-radio-input",
      attrs: { type: "radio", name: "capture-mode", value: id, id: `capture-mode-${id}` },
    }) as HTMLInputElement;
    if (id === "rc_measurement") radio.checked = true;
    modeRadios.set(id, radio);
    modeFieldset.append(radioCard(radio, def.titleRu, def.descriptionRu));
  }

  // --- Источник данных: симулятор или осциллограф ---
  const simulatorRadio = el("input", {
    className: "capture-radio-input",
    attrs: {
      type: "radio",
      name: "capture-source",
      value: "simulator",
      id: "capture-source-simulator",
    },
  }) as HTMLInputElement;
  simulatorRadio.checked = true;
  const deviceRadio = el("input", {
    className: "capture-radio-input",
    attrs: { type: "radio", name: "capture-source", value: "device", id: "capture-source-device" },
  }) as HTMLInputElement;
  const simulatorLabel = radioCard(
    simulatorRadio,
    "Симулятор",
    "Синтетическая запись без железа — безопасно для автоматизации.",
  );
  const deviceLabel = radioCard(
    deviceRadio,
    "Осциллограф Hantek 6022BE",
    "Реальная запись с осциллографа: требуется готовое устройство и пройденный preflight.",
  );
  const sourceFieldset = el("fieldset", { className: "capture-source-group" }, [
    el("legend", { text: "Источник записи" }),
    simulatorLabel,
    deviceLabel,
  ]);

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
  const seriesDisclosure = createDisclosure("Серия и протокол");
  seriesDisclosure.body.append(repeatField.root, intervalField.root, profileField.root);

  const settingsFields = el("div", { className: "capture-settings-grid form-grid" }, [
    durationField.root,
    rateField.root,
    rangeField.root,
    channelsText,
    baselineWrap,
    labelField.root,
  ]);

  const root = el(
    "form",
    {
      className: "capture-form",
      attrs: { novalidate: "" },
    },
    [
      modeFieldset,
      sourceFieldset,
      el("h3", { className: "capture-section-title panel-title", text: "Параметры записи" }),
      settingsFields,
      seriesDisclosure.root,
    ],
  ) as HTMLFormElement;

  const syncModeVisibility = (): void => {
    const mode = handle.getMode();
    channelsText.textContent =
      mode.channels === 2 ? "Каналы: 2 (CH1 + CH2)" : "Каналы: 1 (только CH1)";
    baselineWrap.hidden = !mode.usesBaseline;
    profileField.root.hidden = handle.getSource() !== "simulator";
  };

  root.addEventListener("change", () => {
    syncModeVisibility();
    notify();
  });
  root.addEventListener("input", notify);

  const fieldByErrorKey: Record<string, { setError(message: string | null): void }> = {
    durationS: durationField,
    sampleRateHz: rateField,
    rangeV: rangeField,
    label: labelField,
    baselineSession: baselineField,
    repeat: repeatField,
    intervalS: intervalField,
  };

  const handle: ModeFormHandle = {
    root,
    getMode: () => {
      const checked = [...modeRadios.values()].find((radio) => radio.checked);
      return CAPTURE_MODES[(checked?.value ?? "rc_measurement") as CaptureModeId];
    },
    getSource: () => (deviceRadio.checked ? "device" : "simulator"),
    values: () => ({
      durationS: durationInput.value,
      sampleRateHz: rateInput.value,
      rangeV: rangeSelect.value,
      label: labelInput.value,
      baselineSession: baselineInput.value,
      repeat: repeatInput.value,
      intervalS: intervalInput.value,
      profile: profileSelect.value,
    }),
    setErrors: (errors) => {
      for (const [key, field] of Object.entries(fieldByErrorKey)) {
        field.setError(errors[key as keyof CaptureFieldErrors] ?? null);
      }
    },
    clearErrors: () => {
      for (const field of Object.values(fieldByErrorKey)) field.setError(null);
    },
    onChange: (listener) => {
      listeners.add(listener);
    },
    focusFirstInvalid: () => {
      const firstInvalid = root.querySelector<HTMLInputElement>('[aria-invalid="true"]');
      firstInvalid?.focus();
    },
  };

  syncModeVisibility();
  return handle;
}
