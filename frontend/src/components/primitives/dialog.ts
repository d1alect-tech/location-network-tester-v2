/** Диалоговое окно: ловушка фокуса, Esc, возврат фокуса вызывающему.
 * Русские действия по умолчанию; никакой цветовой индикации состояния. */

import { el } from "./dom";

export interface DialogAction {
  label: string;
  kind?: "primary";
  onClick: (close: () => void) => void;
}

export interface DialogOptions {
  title: string;
  content: Node;
  actions?: DialogAction[];
}

export interface DialogHandle {
  root: HTMLElement;
  close: () => void;
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

function focusables(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (node) => !node.hasAttribute("disabled"),
  );
}

export function openDialog(options: DialogOptions): DialogHandle {
  const invoker = document.activeElement instanceof HTMLElement ? document.activeElement : null;

  const titleId = `lnt-dialog-title-${Math.random().toString(36).slice(2, 10)}`;
  const title = el("h2", { className: "lnt-dialog-title", text: options.title });
  title.id = titleId;

  const closeButton = (): void => handle.close();

  // Пользовательские действия + всегда доступное «Закрыть».
  const resolvedActions: DialogAction[] = [
    ...(options.actions ?? []),
    { label: "Закрыть", onClick: (close) => close() },
  ];
  const actionButtons = resolvedActions.map((action) =>
    el("button", {
      className: action.kind === "primary" ? "lnt-btn lnt-btn-primary" : "lnt-btn",
      text: action.label,
    }),
  );
  resolvedActions.forEach((action, i) => {
    const button = actionButtons[i];
    if (button) button.addEventListener("click", () => action.onClick(closeButton));
  });

  const footer = el("div", { className: "lnt-dialog-actions" }, actionButtons);
  const box = el(
    "div",
    {
      className: "lnt-dialog",
      attrs: {
        role: "dialog",
        "aria-modal": "true",
        "aria-labelledby": titleId,
      },
    },
    [title, options.content, footer],
  );
  const root = el("div", { className: "lnt-dialog-overlay" }, [box]);

  const onKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeButton();
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusables(box);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !box.contains(active))) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first?.focus();
    }
  };
  document.addEventListener("keydown", onKeydown, true);

  const handle: DialogHandle = {
    root,
    close: () => {
      document.removeEventListener("keydown", onKeydown, true);
      root.remove();
      invoker?.focus();
    },
  };

  document.body.append(root);
  const initial = focusables(box)[0];
  initial?.focus();
  return handle;
}
