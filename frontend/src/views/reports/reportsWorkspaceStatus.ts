/** Статус + баннер ошибок рабочей области «Отчёты»: видимая ошибка с повтором.
 * Токены — существующие reports-классы (.lnt-rep-banner) и кнопочная идиома
 * committed-волны (.btn.btn-secondary.lnt-btn); нового CSS не вводится. */

import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";

/** Коды ограничений, при которых отчёт собран, но данные заведомо неполны. */
const DEGRADED_LIMITATION_CODES = [
  "catalog_health_unavailable",
  "values_unavailable",
  "recipes_load_failed",
];

/** Сообщение о деградированной сборке или null, если ограничений нет. */
export function degradedReportMessage(
  limitations: readonly { code: string; detail: string }[],
): string | null {
  const degraded = limitations.filter((item) => DEGRADED_LIMITATION_CODES.includes(item.code));
  if (degraded.length === 0) return null;
  const details = degraded.map((item) => item.detail).join(" ");
  return `Отчёт собран с ограничениями: ${details} Проверьте ограничения и повторите.`;
}

export interface WorkspaceStatusBlock {
  statusHost: HTMLElement;
  errorBanner: HTMLElement;
  setStatus: (text: string) => void;
  showError: (message: string, retry?: () => void) => void;
  setPendingRetry: (retry: () => void) => void;
}

export function createWorkspaceStatusBlock(): WorkspaceStatusBlock {
  const statusHost = el("p", {
    className: "t-compact lnt-helper-text",
    attrs: { role: "status" },
  });
  // statusHost — всегда role=status (прогресс). Ошибки объявляются только
  // через errorBanner role=alert; роль statusHost никогда не переключается,
  // иначе скринридер теряет повторные объявления. setStatus очищает текст
  // перед установкой, чтобы повтор того же сообщения переанонсировался.
  function setStatus(text: string): void {
    statusHost.textContent = "";
    statusHost.textContent = text;
  }
  const errorBanner = el("div", {
    className: "lnt-rep-error lnt-rep-banner lnt-rep-banner-warn",
    attrs: { role: "alert", hidden: "" },
  });
  let pendingRetry: (() => void) | null = null;

  function showError(message: string, retry?: () => void): void {
    errorBanner.replaceChildren(el("p", { className: "lnt-error-text", text: message }));
    const retryButton = el("button", {
      className: "btn btn-secondary lnt-btn",
      text: "Повторить",
      attrs: { type: "button" },
    });
    retryButton.addEventListener("click", () => {
      errorBanner.setAttribute("hidden", "");
      announcePolite("Повторная попытка…");
      (retry ?? pendingRetry)?.();
    });
    errorBanner.append(retryButton);
    errorBanner.removeAttribute("hidden");
    announcePolite(message);
  }

  function setPendingRetry(retry: () => void): void {
    pendingRetry = retry;
  }

  return { statusHost, errorBanner, setStatus, showError, setPendingRetry };
}
