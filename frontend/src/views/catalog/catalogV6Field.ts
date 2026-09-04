/** V6-поле формы каталога: label.field > span.field-label + .ctl.
 * Обёртка label сохраняет связку getByLabel (вопросы a11y/e2e), в отличие
 * от примитива createField (.lnt-field/.lnt-label). Диалоги (overlay) остаются
 * на примитивах — их scope не входит в порт каталога. */

import { el, nextId } from "../../components/primitives/dom";

export function v6Field(labelText: string, control: HTMLElement, hintText?: string): HTMLElement {
  if (!control.id) control.id = nextId("cat-ctl");
  const label = document.createElement("label");
  label.className = "field";
  label.htmlFor = control.id;
  label.append(el("span", { className: "field-label", text: labelText }), control);
  if (hintText !== undefined) {
    const hintId = nextId("cat-hint");
    const hint = el("p", { className: "t-compact", text: hintText, attrs: { id: hintId } });
    label.append(hint);
    const describedBy = control.getAttribute("aria-describedby");
    control.setAttribute("aria-describedby", describedBy ? `${describedBy} ${hintId}` : hintId);
  }
  return label;
}
