/** Вкладки рабочей области экспериментов (T11: выделено из experimentsWorkspace —
 * было 304 чистых LOC). Каркас tablist/tabpanel, ленивое монтирование тяжёлых
 * панелей при первом визите; наполнение панелей и побочные эффекты визита —
 * колбэками владельца. Без смены классов, ARIA и порядка вкладок. */

import { el } from "../../components/primitives/dom";

export interface ExperimentsTabDef {
  key: string;
  label: string;
  paneContent: HTMLElement[];
}

export interface ExperimentsTabsCallbacks {
  /** Первое открытие вкладки: владелец докладывает тяжёлое содержимое в pane. */
  onFirstAttach(key: string, pane: HTMLElement): void;
  /** Каждый выбор вкладки (после attach). */
  onSelect(key: string): void;
}

export interface ExperimentsTabsHandle {
  tabBar: HTMLElement;
  panes: Map<string, HTMLElement>;
  select(key: string): void;
}

export function createExperimentsTabs(
  defs: ExperimentsTabDef[],
  callbacks: ExperimentsTabsCallbacks,
): ExperimentsTabsHandle {
  const tabs = new Map<string, HTMLElement>();
  const panes = new Map<string, HTMLElement>();
  /** Ленивая подгрузка тяжёлых панелей: монтируем содержимое вкладки
   * при первом визите, а не вместе с рабочей областью. */
  const attachedPanes = new Set<string>(["overview"]);

  function attachPane(key: string): void {
    if (attachedPanes.has(key)) return;
    attachedPanes.add(key);
    const pane = panes.get(key);
    if (pane) callbacks.onFirstAttach(key, pane);
  }

  function select(key: string): void {
    attachPane(key);
    for (const [tabKey, button] of tabs) {
      const active = tabKey === key;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.classList.toggle("lnt-cat-tab-active", active);
      button.classList.toggle("is-active", active);
    }
    for (const [paneKey, pane] of panes) pane.hidden = paneKey !== key;
    callbacks.onSelect(key);
  }

  const buttons = defs.map((def) => {
    const button = el("button", {
      className: "lnt-btn lnt-cat-tab snav-item",
      text: def.label,
      attrs: { type: "button", role: "tab", "data-exp-tab": def.key },
    });
    const pane = el(
      "div",
      { attrs: { role: "tabpanel", "aria-label": def.label }, className: "lnt-exp-pane panel" },
      def.paneContent,
    );
    button.addEventListener("click", () => select(def.key));
    tabs.set(def.key, button);
    panes.set(def.key, pane);
    return button;
  });

  const tabBar = el(
    "div",
    {
      className: "lnt-cat-tabs tabbar",
      attrs: { role: "tablist", "aria-label": "Разделы эксперимента" },
    },
    buttons,
  );

  return { tabBar, panes, select };
}
