/** Панель смешивающих факторов трендов (todo 43): чек-лист confound_checklist
 * эксперимента; непроверенный фактор делает связь неинтерпретируемой.
 * C1-лист, выделен из trendView.ts (сменил T11-модуль trendPanels): тексты
 * байт-в-байт, V6-класс .panel сохранён из зафиксированной волны. */

import { el } from "../../components/primitives/dom";

export interface TrendConfoundItem {
  key: string;
  checked: boolean;
  note?: string | null;
}

/** Чек-лист по умолчанию: пуст, пока эксперимент не передал свой. */
export function readTrendConfoundFromRoot(): TrendConfoundItem[] {
  return [];
}

export function buildTrendConfoundPanel(checklist?: TrendConfoundItem[]): HTMLElement {
  const items = checklist ?? readTrendConfoundFromRoot();
  const panel = el("section", { className: "lnt-exp-confound lnt-exp-confound-host panel" });
  panel.append(el("h3", { className: "lnt-exp-subtitle", text: "Смешивающие факторы" }));
  if (items.length === 0) {
    panel.append(
      el("p", { className: "lnt-helper-text", text: "Чек-лист смешивающих факторов пуст." }),
    );
    return panel;
  }
  const list = el("ul", { className: "lnt-exp-limitations" });
  for (const item of items) {
    list.append(
      el("li", {
        text: `${item.key}: ${item.checked ? "проверен" : "НЕ проверен"}${item.note ? ` — ${item.note}` : ""}${item.checked ? "" : " · неконтролируемый смешивающий фактор делает связь неинтерпретируемой"}`,
      }),
    );
  }
  panel.append(list);
  return panel;
}

/** Переставляет панель в хосте: пустой чек-лист снимает её полностью. */
export function renderTrendConfoundChecklist(
  root: HTMLElement,
  checklist: TrendConfoundItem[],
): void {
  const host = root.querySelector(".lnt-exp-confound-host");
  host?.remove();
  if (checklist.length === 0) {
    return;
  }
  root.append(buildTrendConfoundPanel(checklist));
}
