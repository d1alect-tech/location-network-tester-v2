/** Степпер полосы liveStrip (задача 14, зона-карта 13): обёртка
 * СУЩЕСТВУЮЩЕГО числового поля (уровень триггера, #lnt-scope-level).
 * Кнопки −/+ и клавиатура — ←/→/↑/↓ (±шаг), PgUp/PgDn (±1), Home/End
 * (границы ∓/±) — пишут поле и диспечатывают нативное change: живой
 * слушатель листа (scopeTrigger) срабатывает, полоса не дублирует его
 * валидацию и не постит конфиг сама (гейт scopeWorkspace.ts:63). Поле
 * сохраняет свой id и атрибуты; зажим — по границам дескриптора (±5 В). */

import { el } from "../primitives/dom";

export interface LiveStepperDescriptor {
  aria: string;
  step: number;
  min: number;
  max: number;
  minusLabel: string;
  plusLabel: string;
  /** Шаг PgUp/PgDn; по умолчанию 1. */
  stepBig?: number;
}

export interface LiveStepperHandle {
  readonly root: HTMLElement;
}

export function wrapLiveStepper(
  field: HTMLInputElement,
  descriptor: LiveStepperDescriptor,
): LiveStepperHandle {
  const stepBig = descriptor.stepBig ?? 1;
  const minus = el("button", {
    className: "lnt-live-step-btn",
    text: "−",
    attrs: { type: "button", "data-step-dir": "minus", "aria-label": descriptor.minusLabel },
  });
  const plus = el("button", {
    className: "lnt-live-step-btn",
    text: "+",
    attrs: { type: "button", "data-step-dir": "plus", "aria-label": descriptor.plusLabel },
  });
  // Доступное имя полю: метка листа осталась в leftover-панели и для axe
  // не считается (скрыта) — степпер называет поле явно.
  if (!field.hasAttribute("aria-label")) {
    field.setAttribute("aria-label", descriptor.aria);
  }
  const root = el(
    "div",
    { className: "lnt-live-stepper", attrs: { role: "group", "aria-label": descriptor.aria } },
    [minus, field, plus],
  );

  function write(value: number): void {
    const clamped = Math.max(
      descriptor.min,
      Math.min(descriptor.max, Math.round(value * 100) / 100),
    );
    field.value = String(clamped);
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function shift(delta: number): void {
    if (field.value.trim() === "") return;
    const base = Number(field.value);
    if (!Number.isFinite(base)) return;
    write(base + delta);
  }

  minus.addEventListener("click", () => shift(-descriptor.step));
  plus.addEventListener("click", () => shift(descriptor.step));

  field.addEventListener("keydown", (event) => {
    const table: Partial<Record<string, number | "min" | "max">> = {
      ArrowUp: descriptor.step,
      ArrowRight: descriptor.step,
      ArrowDown: -descriptor.step,
      ArrowLeft: -descriptor.step,
      PageUp: stepBig,
      PageDown: -stepBig,
      Home: "min",
      End: "max",
    };
    const action = table[event.key];
    if (action === undefined) return;
    event.preventDefault();
    if (action === "min") {
      write(descriptor.min);
      return;
    }
    if (action === "max") {
      write(descriptor.max);
      return;
    }
    shift(action);
  });

  return { root };
}
