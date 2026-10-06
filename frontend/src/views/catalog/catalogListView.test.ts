/** Фокус roving-навигации переживает пересборку строк: после setItems
 * фокус возвращается строке с тем же идентификатором, а если её снял
 * фильтр — активной строке выдачи, но не <body>. */

import { describe, expect, it } from "vitest";
import type { CatalogSession } from "../../api/types";
import { worstCaseSessions } from "../../testkit/catalogFixture";
import { createCatalogListView } from "./catalogListView";

function mountList(items: CatalogSession[]): {
  root: HTMLElement;
  setItems: (next: CatalogSession[]) => void;
  dispose: () => void;
} {
  const host = document.createElement("div");
  document.body.append(host);
  const list = createCatalogListView({
    onActivate: () => undefined,
    onLoadMore: () => undefined,
    onRetry: () => undefined,
  });
  host.append(list.root);
  list.setItems(items);
  return {
    root: list.root,
    setItems: (next) => list.setItems(next),
    dispose: () => host.remove(),
  };
}

const SESSIONS = worstCaseSessions();

describe("catalogListView: фокус при пересборке", () => {
  it("пересборка выдачи возвращает фокус той же строке", () => {
    const second = SESSIONS[1];
    if (!second) throw new Error("fixture пуста");
    const { root, setItems, dispose } = mountList(SESSIONS);
    try {
      const row = root.querySelector<HTMLElement>(`[data-session-id="${second.id}"]`);
      row?.focus();
      expect(document.activeElement).toBe(row);

      setItems(SESSIONS.slice());

      const again = root.querySelector<HTMLElement>(`[data-session-id="${second.id}"]`);
      expect(document.activeElement).toBe(again);
      expect(document.activeElement).not.toBe(document.body);
    } finally {
      dispose();
    }
  });

  it("строку снял фильтр — фокус на активной строке выдачи, не на body", () => {
    const second = SESSIONS[1];
    const first = SESSIONS[0];
    if (!second || !first) throw new Error("fixture пуста");
    const { root, setItems, dispose } = mountList(SESSIONS);
    try {
      root.querySelector<HTMLElement>(`[data-session-id="${second.id}"]`)?.focus();
      setItems([first]);
      const active = document.activeElement;
      expect(active).not.toBe(document.body);
      expect(active?.getAttribute("data-session-id")).toBe(first.id);
    } finally {
      dispose();
    }
  });

  it("группы дней: один заголовок на день со счётчиком строк", () => {
    const [dayA, dayB] = SESSIONS;
    if (!dayA || !dayB) throw new Error("fixture пуста");
    const sameDay: CatalogSession[] = [
      { ...dayA, id: "a-1", created_utc: "2026-08-05T10:00:00Z" },
      { ...dayB, id: "a-2", created_utc: "2026-08-05T11:00:00Z" },
    ];
    const { root, dispose } = mountList(sameDay);
    try {
      const groups = root.querySelectorAll("tr.cat-group");
      expect(groups.length).toBe(1);
      expect(groups[0]?.querySelector("[data-cat-count]")?.textContent).toBe("2");
    } finally {
      dispose();
    }
  });
});
