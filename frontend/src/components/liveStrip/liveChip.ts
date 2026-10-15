/** Чип + stateless listbox полосы liveStrip (задача 14, зона-карта 13):
 * дискретный выбор >5 значений (частота, 7 опций). Меню принадлежит только
 * своему чипу: открывается кликом или стрелками, Esc и клик мимо закрывают
 * БЕЗ изменений (AC7). Слот [data-slot] показывает ПРИМЕНЁННОЕ значение —
 * staged-цель НИКОГДА не рендерится как текущая (G4): опция-цель помечена
 * «→», aria-selected = применённое. Слушатель закрытия-мимо самозачищается
 * после отцепления корня от документа (утечек нет). */

import { el } from "../primitives/dom";

export interface LiveChipOption {
  value: string;
  text: string;
}

export interface LiveChipDescriptor {
  key: string;
  aria: string;
  options: readonly LiveChipOption[];
  /** Применённое значение — печатается в слоте. */
  current: string;
  menuTitle: string;
}

export interface LiveChipHandle {
  readonly root: HTMLElement;
  /** Переводит применённое значение (после Run); цель гаснет. */
  paintApplied(value: string): void;
  /** Помечает опцию-цель «→» (staged-реестр полосы). */
  markTarget(value: string | null): void;
}

/** Покраска чипа по хосту зоны: слот/aria-selected — применённое, метка
 * «→» — staged-цель. Отдельная функция, чтобы статус-модель вкладки красила
 * чип, не владея хэндлом листа (хэндл замкнут в воркспейсе). */
export function paintLiveChip(
  host: HTMLElement,
  applied: string | null,
  target: string | null,
): void {
  const slot = host.querySelector<HTMLElement>("[data-slot]");
  const options = [...host.querySelectorAll<HTMLElement>("[role='option']")];
  const appliedOption = options.find((option) => option.dataset.value === applied);
  if (slot !== null) {
    slot.textContent = appliedOption?.querySelector(".lnt-live-opt-text")?.textContent ?? "—";
  }
  for (const option of options) {
    option.setAttribute("aria-selected", String(option.dataset.value === applied));
    const mark = option.querySelector<HTMLElement>(".lnt-live-opt-mark");
    if (mark !== null) mark.hidden = option.dataset.value !== target;
  }
}

export function createLiveChip(
  descriptor: LiveChipDescriptor,
  onPick: (value: string) => void,
): LiveChipHandle {
  let applied = descriptor.current;
  let target: string | null = null;
  const slot = el("span", {
    className: "lnt-live-chip-slot",
    attrs: { "data-slot": descriptor.key },
  });
  const chipBtn = el(
    "button",
    {
      className: "lnt-live-chip-btn",
      attrs: {
        type: "button",
        "aria-haspopup": "listbox",
        "aria-expanded": "false",
        "aria-label": `${descriptor.aria}, открыть список`,
      },
    },
    [
      slot,
      el("span", { className: "lnt-live-chip-caret", text: "▾", attrs: { "aria-hidden": "true" } }),
    ],
  );
  const menu = el(
    "div",
    {
      className: "lnt-live-menu",
      attrs: { role: "listbox", "aria-label": descriptor.aria, hidden: "" },
    },
    [el("span", { className: "lnt-live-menu-hd", text: descriptor.menuTitle })],
  );
  const options = descriptor.options.map((option) => {
    const node = el(
      "button",
      {
        className: "lnt-live-opt",
        attrs: {
          type: "button",
          role: "option",
          "aria-selected": "false",
          "data-value": option.value,
          tabindex: "-1",
        },
      },
      [
        el("span", { className: "lnt-live-opt-text", text: option.text }),
        el("span", { className: "lnt-live-opt-mark", text: "→", attrs: { hidden: "" } }),
      ],
    );
    node.addEventListener("click", () => {
      onPick(option.value);
      close(true);
    });
    return node;
  });
  for (const node of options) menu.append(node);
  const root = el("div", { className: "lnt-live-chip", attrs: { "data-ctl": descriptor.key } }, [
    chipBtn,
    menu,
  ]);

  function paint(): void {
    paintLiveChip(root, applied, target);
  }

  function openMenu(): void {
    menu.hidden = false;
    chipBtn.setAttribute("aria-expanded", "true");
    paint();
    const focusTarget =
      options.find((node) => node.dataset.value === target) ??
      options.find((node) => node.dataset.value === applied) ??
      options[0];
    focusTarget?.focus();
  }

  function close(refocus: boolean): void {
    menu.hidden = true;
    chipBtn.setAttribute("aria-expanded", "false");
    if (refocus) chipBtn.focus();
  }

  chipBtn.addEventListener("click", () => {
    if (menu.hidden) openMenu();
    else close(true);
  });
  chipBtn.addEventListener("keydown", (event) => {
    if (!menu.hidden) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openMenu();
    }
  });
  menu.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      // stateless: закрыть без изменений.
      event.preventDefault();
      close(true);
      return;
    }
    if (
      event.key !== "ArrowDown" &&
      event.key !== "ArrowUp" &&
      event.key !== "Home" &&
      event.key !== "End"
    ) {
      return;
    }
    event.preventDefault();
    const index = options.findIndex((node) => node === document.activeElement);
    let next: number;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else if (event.key === "ArrowDown") next = index < 0 ? 0 : (index + 1) % options.length;
    else next = index < 0 ? options.length - 1 : (index - 1 + options.length) % options.length;
    options[next]?.focus();
  });
  const onPointerDown = (event: Event): void => {
    if (!root.isConnected) {
      document.removeEventListener("pointerdown", onPointerDown);
      return;
    }
    if (menu.hidden) return;
    if (root.contains(event.target as Node)) return;
    close(false);
  };
  document.addEventListener("pointerdown", onPointerDown);

  paint();
  return {
    root,
    paintApplied: (value) => {
      applied = value;
      target = null;
      paint();
    },
    markTarget: (value) => {
      target = value;
      paint();
    },
  };
}
