/** Форма режима захвата: mode-first выбор из четырёх режимов, всегда видимые
 * критичные настройки, необязательные разделы за раскрытием. Базовая сессия
 * видима у всех режимов, которые её используют; невозможные поля не
 * показываются. Поля строит modeFormFields.ts, видимость по режиму и
 * источнику живёт в modeFormVisibility.ts — сплит под потолок 250 чистых LOC;
 * разметка, классы и name=-атрибуты не менялись (пины capture.spec.ts). */

import { el } from "../components/primitives/dom";
import { createDisclosure } from "./disclosure";
import { createModeFormFields, radioCard } from "./modeFormFields";
import { syncModeVisibility } from "./modeFormVisibility";
import { CAPTURE_MODES, CAPTURE_MODE_IDS } from "./modes";
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

  // --- Поля записи, базовая сессия и серия ---
  const fields = createModeFormFields();

  // --- Необязательные разделы за раскрытием ---
  const seriesDisclosure = createDisclosure("Серия и протокол");
  seriesDisclosure.body.append(
    fields.repeatField.root,
    fields.intervalField.root,
    fields.profileField.root,
  );

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
      fields.settingsFields,
      seriesDisclosure.root,
    ],
  ) as HTMLFormElement;

  const syncVisibility = (): void => {
    syncModeVisibility(handle.getMode(), handle.getSource(), fields);
  };

  root.addEventListener("change", () => {
    syncVisibility();
    notify();
  });
  root.addEventListener("input", notify);

  const handle: ModeFormHandle = {
    root,
    getMode: () => {
      const checked = [...modeRadios.values()].find((radio) => radio.checked);
      return CAPTURE_MODES[(checked?.value ?? "rc_measurement") as CaptureModeId];
    },
    getSource: () => (deviceRadio.checked ? "device" : "simulator"),
    values: fields.values,
    setErrors: fields.setErrors,
    clearErrors: fields.clearErrors,
    onChange: (listener) => {
      listeners.add(listener);
    },
    focusFirstInvalid: () => {
      const firstInvalid = root.querySelector<HTMLInputElement>('[aria-invalid="true"]');
      firstInvalid?.focus();
    },
  };

  syncVisibility();
  return handle;
}
