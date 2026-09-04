/** Каталог V6: плотная таблица table.tbl.tbl-tight.tbl-cat (строки 28px),
 * группы дней tr.cat-group со счётчиком, сортировка кнопками .cat-sort
 * с aria-sort, счётчик выдачи .cat-found, роли А/Б .cat-role-a/.cat-role-b.
 * Структура повторяет эталон showcase-round2/catalogV6.ts (только чтение).
 *
 * Роли без пары: в каталоге нет слотов сравнения, поэтому чипы помечают
 * активную сессию (А, слот базы) и первого отличного от неё кандидата (Б);
 * без выбора — первые две строки выдачи. Чистая индикация, не состояние.
 *
 * Совместимость e2e (catalog.spec): строки несут .lnt-cat-row +
 * data-session-id, здоровье — текстовой пилюлей .lnt-status-pill (не только
 * цвет), пусто — .lnt-cat-empty, навигация — roving tabindex + Enter.
 * Виртуализация снята: сервер отдаёт страницы по 200 (keyset), рендерятся все
 * загруженные строки — 10k гоняются серверным фильтром, а не окном.
 *
 * T11: строки/группы/сортировка/роли — в catalogListRows; здесь каркас,
 * состояние и навигация. */

import type { CatalogSession } from "../../api/types";
import { clearElement, el } from "../../components/primitives/dom";
import type { RowNav } from "./catalogListNav";
import { handleRowKeys as handleNavKeys, syncRowTabindex } from "./catalogListNav";
import {
  dayKey,
  orderSessions,
  paintSelection,
  renderEmpty,
  renderErrorBanner,
  renderGroup,
  renderRow,
  roleOfSession,
} from "./catalogListRows";
import type { SortDir, SortKey } from "./catalogListRows";

export interface CatalogListOptions {
  onActivate: (session: CatalogSession) => void;
  onLoadMore: () => void;
  onRetry: () => void;
}

export interface CatalogListHandle {
  root: HTMLElement;
  /** Слот панели под тулбар фильтров (.cat-tools) — монтирует workspace. */
  toolsSlot: HTMLElement;
  setItems(items: CatalogSession[], options?: { resetScroll?: boolean }): void;
  setNotice(kind: "loading" | "empty" | "error", message: string): void;
  clearNotice(): void;
  setHasMore(hasMore: boolean): void;
  setSelected(id: string | null): void;
}

export function createCatalogListView(options: CatalogListOptions): CatalogListHandle {
  let items: CatalogSession[] = [];
  let selectedId: string | null = null;
  let activeIndex = 0;
  let firstRender = true;
  let hasMore = false;
  let sort: SortKey = "date";
  let dir: SortDir = "descending";

  const found = el("span", { className: "cat-found", attrs: { "data-cat-found": "" } });
  const toolsSlot = el("div", {
    className: "cat-tools-host",
    attrs: { "data-cat-tools-host": "" },
  });
  const noticeHost = el("div", { className: "cat-notice-host" });
  const tbody = el("tbody");
  const table = el("table", { className: "tbl tbl-tight tbl-cat" });

  const headRow = el("tr", {}, [el("th", { attrs: { scope: "col", "aria-label": "Состояние" } })]);
  const heads = new Map<SortKey, HTMLElement>();
  const dateTitleNodes = new Map<SortKey, Text>();
  const columns: ReadonlyArray<{ key: SortKey; title: string }> = [
    { key: "label", title: "Метка" },
    { key: "type", title: "Тип" },
    { key: "date", title: "Дата" },
  ];
  for (const column of columns) {
    const title = document.createTextNode(column.title);
    if (column.key === "date") dateTitleNodes.set(column.key, title);
    const sortButton = el("button", {
      className: "cat-sort",
      attrs: { type: "button" },
    });
    sortButton.append(
      title,
      el("span", { className: "cat-sort-mark", attrs: { "aria-hidden": "true" } }),
    );
    sortButton.addEventListener("click", () => {
      if (sort === column.key) {
        dir = dir === "ascending" ? "descending" : "ascending";
      } else {
        sort = column.key;
        dir = "ascending";
      }
      render();
    });
    const cell = el(
      "th",
      {
        className: "cat-th",
        attrs: { scope: "col", "data-cat-sort": column.key, "aria-sort": "none" },
      },
      [sortButton],
    );
    heads.set(column.key, cell);
    headRow.append(cell);
  }
  table.append(el("thead", {}, [headRow]), tbody);

  const moreButton = el("button", {
    className: "btn btn-secondary cat-more",
    text: "Показать ещё",
    attrs: { type: "button" },
  });
  moreButton.hidden = true;
  moreButton.addEventListener("click", () => options.onLoadMore());

  const root = el("section", { className: "panel cat-v6 lnt-cat-list" }, [
    el("div", { className: "panel-hd" }, [
      el("h2", { className: "panel-title", text: "Каталог" }),
      found,
    ]),
    toolsSlot,
    el("div", { className: "panel-bd is-bare" }, [
      noticeHost,
      el("div", { className: "tbl-wrap" }, [table]),
      moreButton,
    ]),
  ]);

  function roleOf(sessionId: string): "a" | "b" | null {
    return roleOfSession(items, selectedId, sessionId);
  }

  function render(): void {
    for (const [key, cell] of heads) {
      cell.setAttribute("aria-sort", sort === key ? dir : "none");
    }
    // В группах колонка показывает время — заголовок «Дата» врёт.
    const dateTitle = dateTitleNodes.get("date");
    if (dateTitle) dateTitle.data = sort === "date" ? "Время" : "Дата";
    // Без групп в колонке полная дата — ширины под «14:30» ей мало.
    table.classList.toggle("is-flat", sort !== "date");

    clearElement(tbody);
    const ordered = orderSessions(items, sort, dir);
    const ctx = {
      activeIndex,
      selectedId,
      grouped: sort === "date",
      roleOf,
      onActivate: activate,
      onRowKeys: handleRowKeys,
    };
    if (sort === "date") {
      let day = "";
      let groupRows: HTMLElement[] = [];
      const flushGroup = (): void => {
        if (groupRows.length === 0) return;
        tbody.append(renderGroup(day, groupRows.length));
        for (const row of groupRows) tbody.append(row);
        groupRows = [];
      };
      ordered.forEach((session, position) => {
        const sessionDay = dayKey(session.created_utc);
        if (sessionDay !== day) {
          flushGroup();
          day = sessionDay;
        }
        groupRows.push(renderRow(session, position, { ...ctx, activeIndex }));
      });
      flushGroup();
    } else {
      ordered.forEach((session, position) => {
        tbody.append(renderRow(session, position, { ...ctx, activeIndex }));
      });
    }
    syncFound();
  }

  function syncFound(): void {
    found.textContent = hasMore ? `${items.length}+` : String(items.length);
    found.title = hasMore
      ? `Загружено ${items.length}, есть ещё — нажмите «Показать ещё»`
      : `Загружено сессий: ${items.length}`;
  }

  function activate(index: number): void {
    const session = orderSessions(items, sort, dir)[index];
    if (!session) return;
    activeIndex = index;
    syncRowTabindex(tbody, activeIndex);
    options.onActivate(session);
  }

  const nav: RowNav = {
    body: tbody,
    table,
    count: () => items.length,
    getActive: () => activeIndex,
    setActive: (next) => {
      activeIndex = next;
    },
    onActivate: activate,
    // Близко к концу выдачи — заранее запросить следующую страницу.
    onNearEnd: () => options.onLoadMore(),
    nearEndArmed: () => !moreButton.hidden,
  };

  function handleRowKeys(event: KeyboardEvent, index: number): void {
    handleNavKeys(event, index, nav);
  }

  render();

  return {
    root,
    toolsSlot,
    setItems: (next, opts = {}) => {
      items = next;
      if (opts.resetScroll || firstRender) {
        activeIndex = 0;
        firstRender = false;
      }
      if (activeIndex >= items.length) activeIndex = Math.max(0, items.length - 1);
      render();
    },
    setNotice: (kind, message) => {
      while (noticeHost.firstChild) noticeHost.removeChild(noticeHost.firstChild);
      if (kind === "empty") {
        table.hidden = false;
        moreButton.hidden = true;
        clearElement(tbody);
        tbody.append(renderEmpty(message));
        syncFound();
        return;
      }
      table.hidden = true;
      moreButton.hidden = true;
      if (kind === "error") {
        noticeHost.append(renderErrorBanner(message, () => options.onRetry()));
        return;
      }
      noticeHost.append(
        el("p", { className: "cat-loading t-compact", text: message, attrs: { role: "status" } }),
      );
    },
    clearNotice: () => {
      while (noticeHost.firstChild) noticeHost.removeChild(noticeHost.firstChild);
      table.hidden = false;
      render();
    },
    setHasMore: (nextHasMore) => {
      hasMore = nextHasMore;
      moreButton.hidden = !hasMore || items.length === 0;
      syncFound();
    },
    setSelected: (id) => {
      selectedId = id;
      paintSelection(tbody, selectedId, roleOf);
    },
  };
}
