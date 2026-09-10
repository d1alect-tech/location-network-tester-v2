import { el } from "../../components/primitives/dom";

export function textField(
  labelText: string,
  value: string,
): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = el("input", { className: "lnt-input ctl", attrs: { type: "text" } });
  input.value = value;
  const label = el("label", { className: "lnt-label field-label", text: labelText });
  label.htmlFor = input.id = `wiz-${labelText.replace(/\s+/gu, "-").toLowerCase()}`;
  return { wrap: el("div", { className: "lnt-field field" }, [label, input]), input };
}

export function numberField(
  labelText: string,
  value: number,
): { wrap: HTMLElement; input: HTMLInputElement } {
  const built = textField(labelText, String(value));
  built.input.setAttribute("type", "number");
  built.input.min = "2";
  return built;
}

export function selectField(
  labelText: string,
  options: [string, string][],
  selected?: string,
): { wrap: HTMLElement; input: HTMLSelectElement } {
  const input = el("select", { className: "lnt-select ctl" });
  for (const [value, optionText] of options) {
    const option = el("option", { text: optionText, attrs: { value } });
    if (value === selected) option.selected = true;
    input.append(option);
  }
  const label = el("label", { className: "lnt-label field-label", text: labelText });
  label.htmlFor = input.id = `wiz-${labelText.replace(/\s+/gu, "-").toLowerCase()}`;
  return { wrap: el("div", { className: "lnt-field field" }, [label, input]), input };
}
