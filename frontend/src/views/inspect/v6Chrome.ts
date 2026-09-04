import type { DeviceStatePayload } from "../../api/types-device";
import { clearElement, el } from "../../components/primitives/dom";

/** Сырые значения командбара inspect: билет в capture (C1).
 * Маппинг в нативные параметры capture — в inspectTicket.ticketToCaptureParams. */
export interface InspectCaptureTicket {
  readonly mode: string;
  readonly source: string;
  readonly duration: string;
  readonly rate: string;
  readonly range: string;
  readonly label: string;
}

export type V6ChromeOpts = {
  readonly onCapture: (ticket: InspectCaptureTicket) => void;
};

export type V6Chrome = {
  readonly commandbar: HTMLElement;
  readonly errorBand: HTMLElement;
  showError(msg: string): void;
  hideError(): void;
  /** Живой статус устройства (C1): payload — как есть с бэкенда,
   * null без ошибки — честное «нет данных», null с ошибкой — обрыв связи. */
  setDeviceStatus(payload: DeviceStatePayload | null, error?: string): void;
};

type SelectItem = {
  readonly id: string;
  readonly title: string;
};

function field(labelText: string, controlId: string, control: HTMLElement): HTMLLabelElement {
  return el("label", { className: "cmd-field", attrs: { for: controlId } }, [
    el("span", { className: "cmd-label", text: labelText }),
    control,
  ]);
}

function selectField(label: string, name: string, items: readonly SelectItem[]): HTMLLabelElement {
  const controlId = `cmd-${name}`;
  const node = el("select", { className: "ctl", attrs: { id: controlId, name } });
  for (const item of items) {
    node.append(el("option", { text: item.title, attrs: { value: item.id } }));
  }
  return field(label, controlId, node);
}

function inputField(spec: {
  readonly label: string;
  readonly name: string;
  readonly value: string;
  readonly type: string;
}): HTMLLabelElement {
  const controlId = `cmd-${spec.name}`;
  return field(
    spec.label,
    controlId,
    el("input", {
      className: "ctl",
      attrs: { id: controlId, name: spec.name, type: spec.type, value: spec.value },
    }),
  );
}

function readTicket(form: HTMLFormElement): InspectCaptureTicket {
  const data = new FormData(form);
  const text = (name: string): string => String(data.get(name) ?? "").trim();
  return {
    mode: text("mode"),
    source: text("source"),
    duration: text("duration"),
    rate: text("rate"),
    range: text("range"),
    label: text("label"),
  };
}

function buildDeviceStatus(): HTMLParagraphElement {
  return el("p", {
    className: "cmd-device",
    text: "Устройство: проверка…",
    attrs: { "data-device-status": "", role: "status" },
  }) as HTMLParagraphElement;
}

function renderDeviceStatus(
  node: HTMLParagraphElement,
  payload: DeviceStatePayload | null,
  error?: string,
): void {
  clearElement(node);
  if (payload === null) {
    node.append(
      el("span", {
        className: "lnt-status-pill lnt-tone-warn glyph glyph-warn",
        text: error === undefined ? "Устройство: нет данных" : "Устройство недоступно",
      }),
    );
    if (error !== undefined) {
      node.append(el("span", { className: "cmd-device-desc", text: `: ${error}` }));
    }
    return;
  }
  const ready = payload.state === "ready";
  node.append(
    el("span", {
      className: ready
        ? "lnt-status-pill lnt-tone-ok glyph glyph-ok"
        : "lnt-status-pill lnt-tone-warn glyph glyph-warn",
      text: ready ? "Устройство готово" : "Устройство не готово",
    }),
    el("span", { className: "cmd-device-desc", text: `: ${payload.description_ru}` }),
    el("span", {
      className: "cmd-device-action",
      text: ` Следующее действие: ${payload.recovery_action_ru}`,
    }),
  );
}

function buildCommandbar(
  onCapture: (ticket: InspectCaptureTicket) => void,
  deviceStatus: HTMLParagraphElement,
): HTMLFormElement {
  const submit = el("button", {
    className: "btn",
    text: "Запустить захват",
    attrs: { type: "submit" },
  });
  const commit = (form: HTMLFormElement): void => onCapture(readTicket(form));
  submit.addEventListener("click", (event) => {
    event.preventDefault();
    const form = submit.closest("form");
    if (form instanceof HTMLFormElement) commit(form);
  });
  const form = el("form", { className: "cmdbar", attrs: { "data-showcase": "capture-form" } }, [
    el("div", { className: "cmd-fields" }, [
      selectField("Режим", "mode", [
        { id: "2ch", title: "2 канала" },
        { id: "1ch", title: "1 канал" },
      ]),
      selectField("Источник", "source", [
        { id: "device", title: "устройство" },
        { id: "sim", title: "симуляция" },
      ]),
      inputField({ label: "Длительность с", name: "duration", value: "2.4", type: "number" }),
      inputField({ label: "Частота Гц", name: "rate", value: "48000000", type: "number" }),
      selectField("Диапазон CH1", "range", [
        { id: "2v", title: "±2 В" },
        { id: "5v", title: "±5 В" },
      ]),
      inputField({ label: "Метка", name: "label", value: "", type: "text" }),
    ]),
    el("div", { className: "cmd-actions" }, [submit, deviceStatus]),
  ]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    commit(form);
  });
  return form;
}

export function createV6Chrome(opts: V6ChromeOpts): V6Chrome {
  const errorBand = el("aside", {
    className: "banner banner-inline",
    attrs: { "data-inspect-error": "", role: "alert" },
  });
  errorBand.hidden = true;
  const deviceStatus = buildDeviceStatus();
  return {
    commandbar: buildCommandbar(opts.onCapture, deviceStatus),
    errorBand,
    showError(msg: string): void {
      errorBand.textContent = msg;
      errorBand.hidden = false;
    },
    hideError(): void {
      errorBand.hidden = true;
    },
    setDeviceStatus(payload, error): void {
      renderDeviceStatus(deviceStatus, payload, error);
    },
  };
}
