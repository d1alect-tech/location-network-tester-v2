/** Вкладки рабочей области экспериментов (T11: выделено из experimentsWorkspace —
 * было 304 чистых LOC). Каркас tablist/tabpanel, ленивое монтирование тяжёлых
 * панелей при первом визите; наполнение панелей и побочные эффекты визита —
 * колбэками владельца. Очередь A2: паттерн catalog-табов — стрелки/Home/End
 * двигают фокус, aria-selected отмечает выбор, roving tabindex держит в
 * таб-последовательности один таб (ручная активация: выбор — кликом/Enter). */

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
  const tabs = new Map<string, HTMLButtonElement>();
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

  function paintRoving(focusKey: string): void {
    for (const [tabKey, button] of tabs) button.tabIndex = tabKey === focusKey ? 0 : -1;
  }

  function select(key: string): void {
    attachPane(key);
    for (const [tabKey, button] of tabs) {
      const active = tabKey === key;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.classList.toggle("lnt-cat-tab-active", active);
      button.classList.toggle("is-active", active);
    }
    paintRoving(key);
    for (const [paneKey, pane] of panes) pane.hidden = paneKey !== key;
    callbacks.onSelect(key);
  }

  function focusNeighbour(key: string, delta: number): void {
    const order = defs.map((def) => def.key);
    const next = order[(order.indexOf(key) + delta + order.length) % order.length];
    tabs.get(next ?? key)?.focus();
  }

  function focusEdge(first: boolean): void {
    const edge = first ? defs[0]?.key : defs[defs.length - 1]?.key;
    tabs.get(edge ?? "")?.focus();
  }

  const buttons = defs.map((def, index) => {
    const tabId = `exp-tab-${def.key}`;
    const paneId = `exp-panel-${def.key}`;
    const button = el("button", {
      className: "lnt-btn lnt-cat-tab snav-item",
      text: def.label,
      attrs: {
        type: "button",
        role: "tab",
        id: tabId,
        "aria-controls": paneId,
        "aria-selected": "false",
        tabindex: index === 0 ? "0" : "-1",
        "data-exp-tab": def.key,
      },
    });
    const pane = el(
      "div",
      {
        attrs: { role: "tabpanel", id: paneId, "aria-labelledby": tabId, "aria-label": def.label },
        className: "lnt-exp-pane panel",
      },
      def.paneContent,
    );
    button.addEventListener("click", () => select(def.key));
    button.addEventListener("focus", () => paintRoving(def.key));
    button.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        focusNeighbour(def.key, 1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        focusNeighbour(def.key, -1);
      } else if (event.key === "Home") {
        event.preventDefault();
        focusEdge(true);
      } else if (event.key === "End") {
        event.preventDefault();
        focusEdge(false);
      }
    });
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
