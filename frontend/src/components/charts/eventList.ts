/** Доступный список кандидатов событий (todo 42): role="listbox", полная
 * клавиатурная навигация (стрелки/Enter/Home/End), выбор связан с маркерами
 * на спектрограмме. События — кандидаты, не причины (терминология бэкенда). */

import type { CandidateEventPayload } from "../../api/types-analysis";
import { el } from "../primitives/dom";

export interface EventListHandle {
  root: HTMLElement;
  setEvents(events: readonly CandidateEventPayload[]): void;
  /** Подсвечивает и фокусирует запись; возвращает false, если её нет. */
  focusIndex(index: number): boolean;
  highlight(index: number): void;
  selected(): number | null;
}

function optionText(event: CandidateEventPayload, index: number): string {
  const time = event.peak_time_s.toLocaleString("ru-RU", { maximumFractionDigits: 4 });
  const snr = event.snr.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
  return `Событие ${index + 1}: пик ${time} с · SNR ${snr} · ${event.qualification_status}`;
}

export function createEventList(onSelect: (index: number) => void): EventListHandle {
  let selected: number | null = null;
  const caption = el("p", {
    className: "lnt-event-list-caption",
    text: "Кандидаты событий (список — доступная альтернатива маркерам)",
  });
  const listBox = el("ul", {
    className: "lnt-event-list",
    attrs: { role: "listbox", "aria-label": "Кандидаты событий", tabindex: "0" },
  });

  function options(): HTMLElement[] {
    return Array.from(listBox.querySelectorAll<HTMLElement>("[role='option']"));
  }

  listBox.addEventListener("keydown", (event) => {
    const items = options();
    if (items.length === 0) return;
    const currentIndex = selected ?? -1;
    let next: number | null = null;
    if (event.key === "ArrowDown") next = Math.min(items.length - 1, currentIndex + 1);
    else if (event.key === "ArrowUp") next = Math.max(0, currentIndex - 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else if (event.key === "Enter" || event.key === " ") {
      if (currentIndex >= 0) onSelect(currentIndex);
      event.preventDefault();
      return;
    } else return;
    event.preventDefault();
    if (next !== null) {
      handle.focusIndex(next);
      onSelect(next);
    }
  });

  const handle: EventListHandle = {
    root: el("div", { className: "lnt-event-panel" }, [caption, listBox]),
    setEvents(events) {
      selected = null;
      const nodes = events.map((event, index) => {
        const node = el("li", {
          className: "lnt-event-item",
          text: optionText(event, index),
          attrs: { role: "option", tabindex: "-1", "aria-selected": "false" },
        });
        node.dataset.index = String(index);
        node.addEventListener("click", () => {
          handle.focusIndex(index);
          onSelect(index);
        });
        return node;
      });
      listBox.replaceChildren(...nodes);
      if (nodes.length === 0) {
        listBox.append(
          el("li", { className: "lnt-event-empty", text: "События в этой сессии не обнаружены" }),
        );
      }
    },
    focusIndex(index) {
      const item = options()[index];
      if (item === undefined) return false;
      handle.highlight(index);
      item.focus();
      return true;
    },
    highlight(index) {
      for (const [position, node] of options().entries()) {
        const active = position === index;
        node.setAttribute("aria-selected", active ? "true" : "false");
        node.classList.toggle("is-selected", active);
      }
      selected = index;
    },
    selected: () => selected,
  };
  return handle;
}
