/** Примитивы формы редактора гипотез (C1-лист, выделен из hypothesisEditor):
 * clearEditor/textInput/selectInput — поведение дословно, V6-токены
 * зафиксированной волны (.ctl, .field, .field-label) сохранены. */

import { el } from "../../components/primitives/dom";

export function clearEditor(host: HTMLElement): void {
  while (host.firstChild) host.removeChild(host.firstChild);
}

export function textInput(
  labelText: string,
  value: string,
): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = el("input", { className: "lnt-input ctl", attrs: { type: "text" } });
  input.value = value;
  const label = el("label", { className: "lnt-label field-label", text: labelText });
  label.htmlFor = input.id = `hyp-${labelText.length}-${Math.random().toString(36).slice(2, 7)}`;
  return { wrap: el("div", { className: "lnt-field field" }, [label, input]), input };
}

export interface SelectInputSpec {
  labelText: string;
  options: [string, string][];
  selected?: string;
  disabled?: boolean;
}

export function selectInput(spec: SelectInputSpec): {
  wrap: HTMLElement;
  input: HTMLSelectElement;
} {
  const { labelText, options, selected, disabled = false } = spec;
  const select = el("select", { className: "lnt-select ctl" });
  for (const [value, text] of options) {
    const option = el("option", { text, attrs: { value } });
    if (value === selected) option.selected = true;
    select.append(option);
  }
  if (options.length === 0) select.disabled = true;
  if (disabled && options.length === 0) select.disabled = true;
  const label = el("label", { className: "lnt-label field-label", text: labelText });
  label.htmlFor =
    select.id = `hyp-sel-${labelText.length}-${Math.random().toString(36).slice(2, 7)}`;
  return { wrap: el("div", { className: "lnt-field field" }, [label, select]), input: select };
}
