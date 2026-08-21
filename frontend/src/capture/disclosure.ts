/** Раскрывающийся раздел: кнопка с aria-expanded, управление с клавиатуры,
 * связка aria-controls с областью контента. Токены DESIGN.md. */

import { el, nextId } from "../components/primitives/dom";

export interface DisclosureHandle {
  root: HTMLElement;
  body: HTMLElement;
}

export function createDisclosure(title: string, open = false): DisclosureHandle {
  const bodyId = nextId("lnt-disclosure");
  const body = el("div", {
    className: "lnt-disclosure-body",
    attrs: { id: bodyId, role: "region", "aria-label": title },
  });
  const button = el("button", {
    className: "lnt-btn lnt-disclosure-toggle",
    text: title,
    attrs: { type: "button", "aria-expanded": String(open), "aria-controls": bodyId },
  });
  const applyState = (): void => {
    const expanded = button.getAttribute("aria-expanded") === "true";
    body.hidden = !expanded;
  };
  button.addEventListener("click", () => {
    button.setAttribute(
      "aria-expanded",
      button.getAttribute("aria-expanded") === "true" ? "false" : "true",
    );
    applyState();
  });
  applyState();
  const root = el("div", { className: "lnt-disclosure" }, [button, body]);
  return { root, body };
}
