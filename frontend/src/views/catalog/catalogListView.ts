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
 */

import type { CatalogSession } from "../../api/types";
import { clearElement, el } from "../../components/primitives/dom";
import { HEALTH_LABELS, sessionTypeLabel } from "./catalogModel";

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

type SortKey = "label" | "type" | "date";
type SortDir = "ascending" | "descending";

const DAY_FORMAT = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });

const ROLE_TITLE: Readonly<Record<"a" | "b", string>> = {
  a: "Слот А полосы сравнения: база",
  b: "Слот Б полосы сравнения: сравнение",
};

const GLYPH_BY_TONE: Readonly<Record<string, string>> = {
  ok: "●",
  warn: "▲",
  error: "✕",
};

function dayKey(createdUtc: string | null): string {
  if (!createdUtc) return "unknown";
  const matched = /^(\d{4}-\d{2}-\d{2})/.exec(createdUtc);
  return matched?.[1] ?? "unknown";
}

function formatDay(day: string): string {
  if (day === "unknown") return "Без даты";
  const parsed = new Date(`${day}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? day : DAY_FORMAT.format(parsed);
}

/** В группе день уже назван заголовком — внутри дня различаем время. */
function formatTime(createdUtc: string | null): string {
  if (!createdUtc) return "—";
  const matched = /T(\d{2}):(\d{2})/.exec(createdUtc);
  return matched ? `${matched[1]}:${matched[2]}` : "—";
}

function sortValue(session: CatalogSession, key: SortKey): string {
  if (key === "label") return session.label ?? session.id;
  if (key === "type") return session.session_type ? sessionTypeLabel(session.session_type) : "";
  return session.created_utc ?? "";
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
  const toolsSlot = el("div", { className: "cat-tools-host", attrs: { "data-cat-tools-host": "" } });
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
    sortButton.append(title, el("span", { className: "cat-sort-mark", attrs: { "aria-hidden": "true" } }));
    sortButton.addEventListener("click", () => {
      if (sort === column.key) {
        dir = dir === "ascending" ? "descending" : "ascending";
      } else {
        sort = column.key;
        dir = "ascending";
      }
      render();
    });
    const cell = el("th", {
      className: "cat-th",
      attrs: { scope: "col", "data-cat-sort": column.key, "aria-sort": "none" },
    }, [sortButton]);
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
    const anchor = selectedId ?? items[0]?.id ?? null;
    if (sessionId === anchor) return "a";
    const second = items.find((item) => item.id !== anchor)?.id ?? null;
    if (sessionId === second) return "b";
    return null;
  }

  function renderRow(session: CatalogSession, index: number): HTMLElement {
    const health = HEALTH_LABELS[session.health];
    const row = el("tr", {
      className: `lnt-cat-row${session.id === selectedId ? " lnt-cat-row-selected is-selected" : ""}`,
      attrs: {
        tabindex: index === activeIndex ? "0" : "-1",
        "data-pos": String(index),
        "data-session-id": session.id,
        "data-session": session.id,
        "data-cat-date": dayKey(session.created_utc),
        title: session.storage_path ?? session.id,
      },
    });

    const pill = el("span", { className: `lnt-status-pill lnt-tone-${health.tone}` });
    const glyph = el("span", { attrs: { "aria-hidden": "true" } });
    glyph.textContent = GLYPH_BY_TONE[health.tone] ?? "●";
    pill.append(glyph, document.createTextNode(health.label));
    const stateCell = el("td", {
      className: "lnt-cat-cell",
      attrs: { title: `Состояние: ${health.label}` },
    }, [pill]);

    const labelCell = el("td", { className: "cat-label-cell lnt-cat-cell" });
    const labelText = session.label ?? session.id;
    labelCell.append(
      el("span", {
        className: "cell-ellipsis",
        text: labelText,
        attrs: { "data-cat-label": "", title: session.label ? `Метка: ${session.label}` : labelText },
      }),
    );
    const role = roleOf(session.id);
    if (role !== null) {
      labelCell.append(
        el("span", {
          className: `cat-role cat-role-${role}`,
          text: role === "a" ? "А" : "Б",
          attrs: { "data-cat-role": role, title: ROLE_TITLE[role] },
        }),
      );
    }

    const typeLabel = session.session_type ? sessionTypeLabel(session.session_type) : "—";
    const typeCell = el("td", {
      className: "cell-ellipsis",
      text: typeLabel,
      attrs: { title: typeLabel },
    });

    const grouped = sort === "date";
    const dateText = grouped ? formatTime(session.created_utc) : dayKey(session.created_utc);
    const dateCell = el("td", {
      className: "num",
      text: dateText,
      attrs: { title: session.created_utc ?? dateText },
    });

    row.append(stateCell, labelCell, typeCell, dateCell);
    row.addEventListener("click", () => activate(index));
    row.addEventListener("keydown", (event) => handleRowKeys(event, index));
    return row;
  }

  function renderGroup(day: string, count: number): HTMLElement {
    return el("tr", { className: "cat-group", attrs: { "data-cat-group": day } }, [
      el("th", { attrs: { colspan: "4", scope: "colgroup" } }, [
        el("div", { className: "cat-group-in" }, [
          el("span", { text: formatDay(day) }),
          el("span", {
            className: "cat-group-count",
            text: String(count),
            attrs: { "data-cat-count": "" },
          }),
        ]),
      ]),
    ]);
  }

  function renderEmpty(message: string): HTMLElement {
    return el("tr", {}, [
      el("td", {
        className: "cat-empty lnt-cat-empty",
        text: message,
        attrs: { colspan: "4", "data-cat-empty": "" },
      }),
    ]);
  }

  function orderedItems(): CatalogSession[] {
    const sorted = [...items].sort((left, right) => {
      const order = sortValue(left, sort).localeCompare(sortValue(right, sort), "ru");
      const signed = dir === "ascending" ? order : -order;
      return signed === 0 ? left.id.localeCompare(right.id) : signed;
    });
    return sorted;
  }

  function syncFound(): void {
    found.textContent = hasMore ? `${items.length}+` : String(items.length);
    found.title = hasMore
      ? `Загружено ${items.length}, есть ещё — нажмите «Показать ещё»`
      : `Загружено сессий: ${items.length}`;
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
    const ordered = orderedItems();
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
        groupRows.push(renderRow(session, position));
      });
      flushGroup();
    } else {
      ordered.forEach((session, position) => {
        tbody.append(renderRow(session, position));
      });
    }
    syncFound();
  }

  function activate(index: number): void {
    const session = orderedItems()[index];
    if (!session) return;
    activeIndex = index;
    syncTabindex();
    options.onActivate(session);
  }

  function syncTabindex(): void {
    for (const node of tbody.querySelectorAll<HTMLElement>(".lnt-cat-row")) {
      const index = Number(node.getAttribute("data-pos"));
      node.tabIndex = index === activeIndex ? 0 : -1;
    }
  }

  function ensureVisible(index: number): void {
    const wrap = table.closest(".tbl-wrap");
    const row = tbody.querySelector(`[data-pos="${index}"]`);
    if (!(wrap instanceof HTMLElement) || !(row instanceof HTMLElement)) return;
    const top = row.offsetTop;
    if (top < wrap.scrollTop) wrap.scrollTop = top;
    else if (top + row.offsetHeight > wrap.scrollTop + wrap.clientHeight) {
      wrap.scrollTop = top + row.offsetHeight - wrap.clientHeight;
    }
  }

  function handleRowKeys(event: KeyboardEvent, index: number): void {
    const next =
      event.key === "ArrowDown"
        ? Math.min(items.length - 1, index + 1)
        : event.key === "ArrowUp"
          ? Math.max(0, index - 1)
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : null;
    if (next !== null) {
      event.preventDefault();
      activeIndex = next;
      ensureVisible(next);
      syncTabindex();
      tbody.querySelector<HTMLElement>(`[data-pos="${activeIndex}"]`)?.focus();
      // Близко к концу выдачи — заранее запросить следующую страницу.
      if (items.length - next <= 8 && !moreButton.hidden) options.onLoadMore();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      activate(index);
    }
  }

  /** Точечная перекраска выбора и ролей без пересборки строк (не роняем фокус). */
  function paintSelection(): void {
    for (const node of tbody.querySelectorAll<HTMLElement>(".lnt-cat-row")) {
      const id = node.getAttribute("data-session-id");
      const isSelected = id === selectedId;
      node.classList.toggle("lnt-cat-row-selected", isSelected);
      node.classList.toggle("is-selected", isSelected);
      node.querySelector(".cat-role")?.remove();
      if (id !== null) {
        const role = roleOf(id);
        if (role !== null) {
          node.querySelector(".cat-label-cell")?.append(
            el("span", {
              className: `cat-role cat-role-${role}`,
              text: role === "a" ? "А" : "Б",
              attrs: { "data-cat-role": role, title: ROLE_TITLE[role] },
            }),
          );
        }
      }
    }
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
        const banner = el("div", {
          className: "banner banner-inline lnt-cat-error",
          attrs: { role: "alert" },
        });
        banner.append(
          el("span", { className: "banner-glyph", text: "✕", attrs: { "aria-hidden": "true" } }),
          el("p", { className: "banner-msg", text: message }),
          el("button", { className: "btn btn-secondary", text: "Повторить", attrs: { type: "button" } }),
        );
        banner.querySelector("button")?.addEventListener("click", () => options.onRetry());
        noticeHost.append(banner);
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
      paintSelection();
    },
  };
}
