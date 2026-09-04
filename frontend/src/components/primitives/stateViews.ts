/** Повторяемый блок ошибки с кнопкой повтора (очередь A1).
 * Русское сообщение — через role=alert; кнопка — .lnt-btn (цель 44px
 * и фокус 2px из primitives.css). Используют списки и детали
 * экспериментов/отчётов, чтобы ошибка не была тупиком. */

import { el } from "./dom";

export function errorWithRetry(
  message: string,
  onRetry: () => void,
  retryLabel = "Повторить загрузку",
): HTMLElement {
  const button = el("button", {
    className: "lnt-btn btn-secondary",
    text: retryLabel,
    attrs: { type: "button" },
  });
  button.addEventListener("click", () => onRetry());
  return el("div", { className: "lnt-state-error" }, [
    el("p", { className: "lnt-helper-text", text: message, attrs: { role: "alert" } }),
    button,
  ]);
}
