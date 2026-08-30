import { el } from "../../components/primitives/dom";

export type V6ChromeOpts = {
  readonly onCapture: () => void;
};

export type V6Chrome = {
  readonly commandbar: HTMLElement;
  readonly errorBand: HTMLElement;
  showError(msg: string): void;
  hideError(): void;
};

type SelectItem = {
  readonly id: string;
  readonly title: string;
};

function field(label: string, control: HTMLElement): HTMLLabelElement {
  return el("label", { className: "cmd-field" }, [
    el("span", { className: "cmd-label", text: label }),
    control,
  ]);
}

function selectField(label: string, name: string, items: readonly SelectItem[]): HTMLLabelElement {
  const node = el("select", { className: "ctl", attrs: { name } });
  for (const item of items) {
    node.append(el("option", { text: item.title, attrs: { value: item.id } }));
  }
  return field(label, node);
}

function inputField(spec: {
  readonly label: string;
  readonly name: string;
  readonly value: string;
  readonly type: string;
}): HTMLLabelElement {
  return field(
    spec.label,
    el("input", { className: "ctl", attrs: { name: spec.name, type: spec.type, value: spec.value } }),
  );
}

function buildCommandbar(onCapture: () => void): HTMLFormElement {
  const submit = el("button", {
    className: "btn",
    text: "Запустить захват",
    attrs: { type: "submit" },
  });
  submit.addEventListener("click", (event) => {
    event.preventDefault();
    onCapture();
  });
  const form = el(
    "form",
    { className: "cmdbar", attrs: { "data-showcase": "capture-form" } },
    [
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
      el("div", { className: "cmd-actions" }, [submit]),
    ],
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  return form;
}

export function createV6Chrome(opts: V6ChromeOpts): V6Chrome {
  const errorBand = el("aside", {
    className: "banner banner-inline",
    attrs: { "data-inspect-error": "", role: "alert" },
  });
  errorBand.hidden = true;
  return {
    commandbar: buildCommandbar(opts.onCapture),
    errorBand,
    showError(msg: string): void {
      errorBand.textContent = msg;
      errorBand.hidden = false;
    },
    hideError(): void {
      errorBand.hidden = true;
    },
  };
}
