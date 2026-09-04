/** Строка алёрта раздела «Захват» на тонах T10: err — блокирующая ошибка
 * (role=alert), warn — осознанная блокировка с причиной, info — подсказка
 * (role=status). Выделено из captureView ради лимита 250 чистых LOC. */

import { ApiError } from "../api/errors";
import { el } from "../components/primitives/dom";
import { announcePolite } from "../components/primitives/status";

export type CaptureAlertTone = "err" | "warn" | "info";

export interface CaptureAlertHandle {
  readonly line: HTMLElement;
  show(message: string, tone?: CaptureAlertTone): void;
  hide(): void;
  /** Показывает ошибку API; при disposed молча игнорирует. */
  showApiError(error: unknown, disposed: boolean): void;
}

export function createCaptureAlert(): CaptureAlertHandle {
  const line = el("p", {
    className: "capture-alert banner banner-inline banner-err",
    attrs: { role: "alert" },
  });
  line.hidden = true;

  const show = (message: string, tone: CaptureAlertTone = "err"): void => {
    line.className = `capture-alert banner banner-inline banner-${tone}`;
    line.setAttribute("role", tone === "err" ? "alert" : "status");
    line.textContent = message;
    line.hidden = false;
    announcePolite(message);
  };
  const hide = (): void => {
    line.hidden = true;
  };
  const showApiError = (error: unknown, disposed: boolean): void => {
    if (disposed) return;
    if (error instanceof ApiError && error.kind === "conflict") {
      show("Сервер сообщил конфликт: уже выполняется другая задача (HTTP 409).");
      return;
    }
    show(
      error instanceof Error ? `Операция не выполнена: ${error.message}` : "Операция не выполнена.",
    );
  };

  return { line, show, hide, showApiError };
}
