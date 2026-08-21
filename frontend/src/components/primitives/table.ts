/** Таблица данных: клавиатурная навигация по строкам, сортируемые заголовки,
 * статусы с текстом и глифом (не только цвет), русские состояния.
 * По умолчанию строки упорядочены по идентификатору (стабильный базовый порядок). */

import { clearElement, el } from "./dom";

export interface StatusCue {
  tone: "ok" | "warn" | "error";
  label: string;
}

export interface TableColumn<T> {
  key: string;
  header: string;
  sortable?: boolean;
  value: (row: T) => string;
  status?: (row: T) => StatusCue;
}

export type TableState<T> =
  | { kind: "data"; rows: T[] }
  | { kind: "loading" }
  | { kind: "error"; onRetry: () => void }
  | { kind: "empty" };

export interface DataTableHandle<T> {
  root: HTMLElement;
  setState(state: TableState<T>): void;
}

const TONE_GLYPHS: Record<StatusCue["tone"], string> = {
  ok: "●",
  warn: "▲",
  error: "✕",
};

function rowId<T>(row: T): string {
  const id = (row as Record<string, unknown>).id;
  return typeof id === "string" ? id : "";
}

export function createDataTable<T>(
  columns: TableColumn<T>[],
  options: { emptyText?: string; caption?: string } = {},
): DataTableHandle<T> {
  const root = el("div", { className: "lnt-table-wrapper" });
  let sortState: { key: string; dir: "asc" | "desc" } | null = null;
  let rows: T[] = [];
  let headerCells: HTMLTableCellElement[] = [];
  let tbody: HTMLElement | null = null;

  function orderedRows(): T[] {
    const base = [...rows].sort((a, b) => rowId(a).localeCompare(rowId(b), "ru"));
    if (sortState === null) return base;
    const column = columns.find((c) => c.key === sortState?.key);
    if (!column) return base;
    const dir = sortState.dir === "asc" ? 1 : -1;
    return base.sort((a, b) => dir * column.value(a).localeCompare(column.value(b), "ru"));
  }

  function refreshSortAttributes(): void {
    for (const [index, column] of columns.entries()) {
      const th = headerCells[index];
      if (!th) continue;
      th.setAttribute(
        "aria-sort",
        sortState?.key === column.key
          ? sortState.dir === "asc"
            ? "ascending"
            : "descending"
          : "none",
      );
    }
  }

  function renderBody(): void {
    if (!tbody) return;
    clearElement(tbody);
    const trs = orderedRows().map((row) => {
      const tr = el("tr", { className: "lnt-row", attrs: { tabindex: "-1" } });
      for (const column of columns) {
        const td = document.createElement("td");
        const cue = column.status?.(row);
        if (cue) {
          const glyph = el("span", {
            className: "lnt-status-glyph",
            text: TONE_GLYPHS[cue.tone],
          });
          glyph.setAttribute("aria-hidden", "true");
          const pill = el("span", { className: `lnt-status-pill lnt-tone-${cue.tone}` }, [glyph]);
          pill.append(document.createTextNode(cue.label));
          td.append(pill);
        } else {
          td.textContent = column.value(row);
        }
        tr.append(td);
      }
      return tr;
    });

    trs.forEach((tr, index) => {
      tr.addEventListener("keydown", (event) => {
        const delta = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
        if (delta === 0) return;
        event.preventDefault();
        const target = trs[trs.indexOf(tr) + delta];
        if (!target) return;
        for (const other of trs) other.setAttribute("tabindex", "-1");
        target.setAttribute("tabindex", "0");
        target.focus();
      });
      if (index === 0) tr.setAttribute("tabindex", "0");
    });
    tbody.append(...trs);
  }

  function renderData(): void {
    clearElement(root);
    root.removeAttribute("aria-busy");

    headerCells = columns.map((column) => {
      const th = el("th", { attrs: { scope: "col" } });
      if (column.sortable) {
        const button = el("button", { className: "lnt-th-sort", text: column.header });
        button.addEventListener("click", () => {
          sortState =
            sortState?.key === column.key
              ? { key: column.key, dir: sortState.dir === "asc" ? "desc" : "asc" }
              : { key: column.key, dir: "asc" };
          refreshSortAttributes();
          renderBody();
        });
        th.append(button);
      } else {
        th.textContent = column.header;
      }
      return th;
    });
    tbody = el("tbody");
    const table = el("table", { className: "lnt-table" }, [
      el("thead", {}, [el("tr", {}, headerCells)]),
      tbody,
    ]);
    if (options.caption) table.append(el("caption", { text: options.caption }));
    root.append(table);

    refreshSortAttributes();
    renderBody();
  }

  return {
    root,
    setState: (state) => {
      switch (state.kind) {
        case "data":
          rows = state.rows;
          renderData();
          break;
        case "loading":
          clearElement(root);
          root.setAttribute("aria-busy", "true");
          root.append(el("p", { className: "lnt-table-note", text: "Загрузка…" }));
          break;
        case "empty":
          clearElement(root);
          root.removeAttribute("aria-busy");
          root.append(
            el("p", {
              className: "lnt-table-note",
              text: options.emptyText ?? "Сессии не найдены.",
            }),
          );
          break;
        case "error": {
          clearElement(root);
          root.removeAttribute("aria-busy");
          const note = el("p", {
            className: "lnt-table-note",
            text: "Ошибка загрузки. Проверьте соединение и повторите.",
          });
          const retry = el("button", { className: "lnt-btn", text: "Повторить" });
          retry.addEventListener("click", () => state.onRetry());
          root.append(note, retry);
          break;
        }
      }
    },
  };
}
