/** Компактная сегмент-группа полосы liveStrip (задача 14, зона-карта 13):
 * дискретный выбор ≤5 значений — нативные кнопки с aria-pressed (один скин
 * кликабельности: рамка на хроме = кнопка). Клик по нажатому — no-op;
 * стрелки ←/→ двигают фокус И активируют соседний сегмент — значения идут
 * той же дорожкой, что и клик; Enter/Space — нативная активация кнопки.
 * Группа несёт data-ctl (манифестный контроль) или data-local (локальный);
 * контрактные id/классы листа (напр. #lnt-scope-vdiv + .lnt-scope-seg)
 * передаются дескриптором и сохраняются при ре-паренте полосой. */

import { el } from "../primitives/dom";

export interface LiveSegOption {
  value: string;
  text: string;
}

export interface LiveSegDescriptor {
  /** Ключ группы: data-ctl (манифестный) или data-local (локальный). */
  key: string;
  kind: "ctl" | "local";
  aria: string;
  options: readonly LiveSegOption[];
  current: string;
  /** Контрактные атрибуты группы (id ре-парента, напр. #lnt-scope-vdiv). */
  groupAttrs?: Record<string, string>;
  /** Контрактный класс группы (напр. lnt-scope-seg). */
  groupClassName?: string;
}

export interface LiveSegHandle {
  readonly root: HTMLElement;
  selection(): string;
  /** Переводит нажатое состояние по истине сервиса, БЕЗ вызова onPick. */
  paint(current: string): void;
  /** Программная активация через ту же дорожку (сброс/автосет, задачи 15). */
  pick(value: string): void;
}

export function createLiveSeg(
  descriptor: LiveSegDescriptor,
  onPick: (value: string) => void,
): LiveSegHandle {
  let current = descriptor.current;
  const buttons = new Map<string, HTMLButtonElement>();
  for (const option of descriptor.options) {
    buttons.set(
      option.value,
      el("button", {
        className: "lnt-live-seg-btn",
        text: option.text,
        attrs: {
          type: "button",
          "data-value": option.value,
          "aria-pressed": String(option.value === current),
        },
      }),
    );
  }
  const root = el(
    "div",
    {
      className: `lnt-live-seg${descriptor.groupClassName ? ` ${descriptor.groupClassName}` : ""}`,
      attrs: {
        role: "group",
        "aria-label": descriptor.aria,
        [descriptor.kind === "local" ? "data-local" : "data-ctl"]: descriptor.key,
        ...descriptor.groupAttrs,
      },
    },
    [...buttons.values()],
  );

  function paint(next: string): void {
    current = next;
    for (const [value, button] of buttons) {
      button.setAttribute("aria-pressed", String(value === current));
    }
  }

  function apply(value: string): void {
    if (value === current) return;
    paint(value);
    onPick(value);
  }

  for (const [value, button] of buttons) {
    button.addEventListener("click", () => apply(value));
  }

  root.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const order = [...buttons.values()];
    const active = document.activeElement;
    const index = active instanceof HTMLButtonElement ? order.indexOf(active) : -1;
    if (index < 0) return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = order[(index + delta + order.length) % order.length];
    if (next === undefined) return;
    next.focus();
    next.click();
  });

  return {
    root,
    selection: () => current,
    paint,
    pick: (value) => {
      if (buttons.has(value)) apply(value);
    },
  };
}
