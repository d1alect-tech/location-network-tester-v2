/** V6 RED-контракты раздела «Каталог» (TDD RED, T2).
 * Эталон классов: showcase-round2/kit.css + variantV6.css (только чтение).
 * Каждый тест ниже называет точный V6-класс/селектор-разрыв и падает
 * по причине missing class — НЕ import-ошибки. Зелёный пин один:
 * shell уже помечает активный таб .snav-item.is-active (полоса ::before в CSS). */

import { describe, expect, it } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { CatalogSession } from "../../api/types";
import { createV6ShellHeader } from "../../shell/v6Shell";
import { RouteStore } from "../../state/routeState";
import { createCatalogListView } from "./catalogListView";
import { mountCatalogWorkspace } from "./catalogWorkspace";

const SESSIONS: CatalogSession[] = [
  {
    id: "capture-00001",
    health: "ok",
    created_utc: "2026-08-29T10:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "bad",
    label: "стенд-А",
    storage_path: null,
  },
  {
    id: "capture-00002",
    health: "ok",
    created_utc: "2026-08-29T11:00:00Z",
    source: "capture",
    session_type: "capture",
    profile: "quiet",
    label: "стенд-Б",
    storage_path: null,
  },
];

function stubClient(): LntApiClient {
  return {
    catalogSessions: async () => ({ items: [], next_cursor: null }),
  } as unknown as LntApiClient;
}

function mountList(): { root: HTMLElement; dispose: () => void } {
  const host = document.createElement("div");
  const list = createCatalogListView({
    onActivate: () => undefined,
    onLoadMore: () => undefined,
    onRetry: () => undefined,
  });
  host.append(list.root);
  list.setItems(SESSIONS);
  return { root: list.root, dispose: () => host.remove() };
}

describe("каталог V6: плотная таблица 28px", () => {
  it("список — table.tbl.tbl-tight.tbl-cat, строки 28px", () => {
    // Given: две сессии в выдаче
    const { root, dispose } = mountList();
    try {
      // Then: V6-таблица каталога (§2.3 kit.css, .cat-v6 .tbl-cat td 28px)
      const table = root.querySelector("table.tbl.tbl-tight.tbl-cat");
      expect(
        table,
        "V6-разрыв: нет table.tbl.tbl-tight.tbl-cat (сейчас виртуализованные div.lnt-cat-row)",
      ).not.toBeNull();
    } finally {
      dispose();
    }
  });
});

describe("каталог V6: сортировка, группы дней, роли А/Б", () => {
  it("шапка — кнопки .cat-sort с aria-sort и глифом направления", () => {
    // Given
    const { root, dispose } = mountList();
    try {
      // Then: заголовок колонки — настоящая кнопка .cat-sort (§6, variantV6.css)
      const sort = root.querySelector("th .cat-sort");
      expect(
        sort,
        "V6-разрыв: нет th .cat-sort (сортировка недоступна с клавиатуры)",
      ).not.toBeNull();
      expect(sort?.closest("th")?.hasAttribute("aria-sort")).toBe(true);
    } finally {
      dispose();
    }
  });

  it("группы дней .cat-group и роли строк .cat-role-a/.cat-role-b", () => {
    // Given
    const { root, dispose } = mountList();
    try {
      // Then: заголовок дня .cat-group + роль А/Б у строки (§4, variantV6.css)
      expect(
        root.querySelector("tr.cat-group"),
        "V6-разрыв: нет tr.cat-group (дни как группы)",
      ).not.toBeNull();
      expect(
        root.querySelector(".cat-role-a"),
        "V6-разрыв: нет .cat-role-a (роль не связывает строку с полосой пары)",
      ).not.toBeNull();
      expect(
        root.querySelector(".cat-role-b"),
        "V6-разрыв: нет .cat-role-b",
      ).not.toBeNull();
    } finally {
      dispose();
    }
  });
});

describe("каталог V6: тулбар и инлайн-баннер", () => {
  it("панель инструментов .cat-tools с полем .ctl", () => {
    // Given: смонтированная рабочая область каталога
    const host = document.createElement("div");
    const routes = new RouteStore();
    const dispose = mountCatalogWorkspace(host, { client: stubClient(), routes });
    try {
      // Then: тулбар V6 (§2.3: инпут 32px, цель §6 ≥ 28px)
      const tools = host.querySelector(".cat-tools");
      expect(
        tools,
        "V6-разрыв: нет .cat-tools над таблицей каталога",
      ).not.toBeNull();
      expect(
        tools?.querySelector("input.ctl, select.ctl"),
        "V6-разрыв: в .cat-tools нет контрола .ctl",
      ).not.toBeNull();
    } finally {
      dispose();
      routes.dispose();
      host.remove();
    }
  });

  it("ошибка списка — .banner.banner-inline, а не голый текст", () => {
    // Given: состояние ошибки выдачи
    const host = document.createElement("div");
    const list = createCatalogListView({
      onActivate: () => undefined,
      onLoadMore: () => undefined,
      onRetry: () => undefined,
    });
    host.append(list.root);
    list.setNotice("error", "Ошибка загрузки.");
    try {
      // Then: V6-полоса ошибки 32px (variantV6.css .banner-inline)
      const banner = list.root.querySelector(".banner.banner-inline");
      expect(
        banner,
        "V6-разрыв: нет .banner.banner-inline для ошибки списка",
      ).not.toBeNull();
      expect(banner?.getAttribute("role")).toBe("alert");
    } finally {
      host.remove();
    }
  });
});

describe("каталог V6: активный таб (пин, уже зелёный)", () => {
  it("shell помечает каталог .snav-item.is-active с aria-current", () => {
    // Given / When
    const { root } = createV6ShellHeader({ activeRoute: "catalog" });

    // Then: активный таб — полоса 2px ::before + aria-current=page (kit.css)
    const active = root.querySelector("#nav-catalog.snav-item.is-active");
    expect(active).not.toBeNull();
    expect(active?.getAttribute("aria-current")).toBe("page");
  });
});
