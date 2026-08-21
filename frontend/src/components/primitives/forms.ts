/** Поля форм: программная связка label↔control, русские тексты ошибок,
 * состояние ожидания мутации для кнопки отправки. */

import type { Mutation } from "../../state/resource";
import { el, nextId } from "./dom";

export interface FieldHandle {
  root: HTMLElement;
  controlId: string;
  /** Показывает ошибку валидации; null — очистить состояние. */
  setError(message: string | null): void;
}

export function createField(options: {
  label: string;
  control: HTMLElement;
  hintText?: string;
}): FieldHandle {
  const controlId = options.control.id || nextId("lnt-field");
  options.control.id = controlId;

  const label = el("label", { className: "lnt-label", text: options.label });
  label.htmlFor = controlId;

  const errorId = nextId("lnt-field-error");
  const hint = options.hintText
    ? el("p", { className: "lnt-hint", text: options.hintText, attrs: { id: nextId("lnt-hint") } })
    : null;

  const root = el("div", { className: "lnt-field" }, [label, options.control]);
  if (hint) root.append(hint);

  return {
    root,
    controlId,
    setError: (message) => {
      const existing = root.querySelector('[role="alert"]');
      if (message === null) {
        existing?.remove();
        options.control.removeAttribute("aria-describedby");
        options.control.setAttribute("aria-invalid", "false");
        return;
      }
      let alert = existing;
      if (alert === null) {
        alert = el("p", { className: "lnt-error-text" });
        alert.id = errorId;
        alert.setAttribute("role", "alert");
        root.append(alert);
        const describedBy = [hint?.id, errorId].filter((part) => part !== undefined).join(" ");
        options.control.setAttribute("aria-describedby", describedBy);
      }
      alert.textContent = message;
      options.control.setAttribute("aria-invalid", "true");
    },
  };
}

/** Синхронизирует блокировку submit-контролов с состоянием мутации:
 * pending → disabled + aria-busy; иначе контролы активны. */
export function setFormPending(form: HTMLFormElement, mutation: Mutation<unknown, unknown>): void {
  const pending = mutation.get().kind === "pending";
  for (const button of form.querySelectorAll<HTMLButtonElement>('button[type="submit"], button')) {
    button.disabled = pending;
  }
  form.setAttribute("aria-busy", pending ? "true" : "false");
}
