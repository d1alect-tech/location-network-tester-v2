/** Ошибка с повтором: идиома spectrogramPanel (баннер role=alert + кнопка
 * «Повторить»). Тексты — через textContent, без innerHTML. */

import { el } from "./dom";

/** Баннер ошибки с кнопкой повтора; повтор делегируется вызывающей стороне. */
export function errorWithRetry(
  message: string,
  onRetry: () => void,
  retryLabel = "Повторить",
): HTMLElement {
  const box = el("div", { className: "lnt-error-retry", attrs: { role: "alert" } });
  box.append(el("p", { className: "lnt-error-text", text: message }));
  const retry = el("button", {
    className: "lnt-btn",
    text: retryLabel,
    attrs: { type: "button" },
  });
  retry.addEventListener("click", onRetry);
  box.append(retry);
  return box;
}
