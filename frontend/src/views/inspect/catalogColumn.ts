import type { CatalogSession } from "../../api/types";
import { clearElement, el } from "../../components/primitives/dom";
import { type CatalogSort, type SortDir, buildCatalogRows } from "./catalogColumnModel";
import { renderCatalogRow } from "./catalogColumnRender";
import type { JoinedCatalogClient } from "./catalogJoinedSource";
import { joinKey, loadJoinedCatalog } from "./catalogJoinedSource";
import type { PairSlot, PairStateHandle } from "./pairState";

export type CatalogColumnClient = JoinedCatalogClient;

export interface CatalogColumnOptions {
  readonly client: CatalogColumnClient;
  readonly pair: PairStateHandle;
  readonly onPick: (loadKey: string) => void;
  /** M1 (todo 4): точное назначение слота кнопкой «А»/«Б» строки;
   * провод к pair.assignSlot появляется в todo 5 (inspectV6). */
  readonly onAssign?: (slot: PairSlot, loadKey: string) => void;
}

export interface CatalogColumnHandle {
  readonly root: HTMLElement;
  reload(): Promise<void>;
  /** Слот-клик pairbar (todo 5): фокус возвращается на первый ряд рейла. */
  focusRail(slot: PairSlot): void;
}

function assertNever(value: never): never {
  throw new Error(`unhandled catalog sort ${String(value)}`);
}

function ariaSortValue(dir: SortDir): "ascending" | "descending" {
  return dir === "asc" ? "ascending" : "descending";
}

export function createCatalogColumn(opts: CatalogColumnOptions): CatalogColumnHandle {
  let sort: CatalogSort = "date";
  let dir: SortDir = "desc";
  let query = "";
  let sessions: readonly CatalogSession[] = [];
  let analyzedByDir: ReadonlyMap<string, boolean> = new Map();
  let invalidByDir: ReadonlyMap<string, string> = new Map();
  let activeSession: string | null = null;

  const found = el("span", { className: "cat-found", attrs: { "data-cat-found": "" } });
  const search = el("input", {
    className: "cat-search",
    attrs: {
      type: "search",
      "data-cat-search": "",
      "aria-label": "Поиск по метке",
      placeholder: "Поиск по метке",
    },
  });
  const clear = el("button", {
    attrs: { type: "button", "data-cat-clear": "" },
    text: "Сбросить",
  });

  const labelBtn = el("button", {
    className: "cat-sort",
    text: "Метка",
    attrs: { type: "button", "data-cat-sort": "label", "aria-sort": "none" },
  });
  const dateBtn = el("button", {
    className: "cat-sort",
    text: "Дата",
    attrs: { type: "button", "data-cat-sort": "date", "aria-sort": "none" },
  });
  const sortbar = el("div", { className: "cat-sortbar" }, [labelBtn, dateBtn]);
  const tbody = el("tbody");
  const table = el("table", { className: "tbl tbl-cat" }, [tbody]);

  const root = el("section", { className: "panel cat-v6" }, [
    el("div", { className: "panel-hd" }, [
      el("h2", { className: "panel-title", text: "Каталог" }),
      found,
    ]),
    el("div", { className: "cat-tools" }, [search, clear, sortbar]),
    table,
  ]);

  function syncAriaSort(): void {
    switch (sort) {
      case "label":
        labelBtn.setAttribute("aria-sort", ariaSortValue(dir));
        dateBtn.setAttribute("aria-sort", "none");
        return;
      case "date":
        dateBtn.setAttribute("aria-sort", ariaSortValue(dir));
        labelBtn.setAttribute("aria-sort", "none");
        return;
      default:
        assertNever(sort);
    }
  }

  function render(): void {
    syncAriaSort();
    const rows = buildCatalogRows({ sessions, sort, dir, query });
    const pair = opts.pair.get();
    clearElement(tbody);
    let visible = 0;
    for (const row of rows) {
      if (row.kind === "session") visible += 1;
      tbody.append(
        renderCatalogRow(row, {
          grouped: sort === "date",
          pair,
          analyzedOf: (session) => analyzedByDir.get(joinKey(session)),
          invalidOf: (session) => invalidByDir.get(joinKey(session)),
          onPick: (key) => {
            opts.onPick(key);
            const escaped = CSS.escape(key);
            tbody
              .querySelector<HTMLElement>(
                `tr[data-rowkey="${escaped}"], tr[data-session="${escaped}"]`,
              )
              ?.focus();
          },
          onAssign: (slot, key) => {
            opts.onAssign?.(slot, key);
            // Фокус re-grab — паттерн onPick-замыкания: пара меняется,
            // render пересобирает tbody, фокус возвращается на ту же строку.
            const escaped = CSS.escape(key);
            tbody
              .querySelector<HTMLElement>(
                `tr[data-rowkey="${escaped}"], tr[data-session="${escaped}"]`,
              )
              ?.focus();
          },
          onFocus: (id) => {
            activeSession = id;
          },
        }),
      );
    }
    const renderedSessions = [...tbody.querySelectorAll<HTMLElement>("tr[data-rowkey]")];
    const active = renderedSessions.find(
      (row) => row.dataset.rowkey === activeSession || row.dataset.session === activeSession,
    );
    const tabStop = active ?? renderedSessions[0];
    if (tabStop !== undefined) {
      tabStop.tabIndex = 0;
      activeSession = tabStop.dataset.rowkey ?? tabStop.dataset.session ?? null;
    }
    found.textContent = String(visible);
  }

  function cycleLabelSort(): void {
    if (sort !== "label") {
      sort = "label";
      dir = "asc";
      return;
    }
    if (dir === "asc") {
      dir = "desc";
      return;
    }
    sort = "date";
    dir = "desc";
  }

  labelBtn.addEventListener("click", () => {
    cycleLabelSort();
    render();
  });
  dateBtn.addEventListener("click", () => {
    sort = "date";
    dir = "desc";
    render();
  });
  search.addEventListener("input", () => {
    query = search.value;
    render();
  });
  clear.addEventListener("click", () => {
    search.value = "";
    query = "";
    render();
  });
  opts.pair.subscribe(() => {
    render();
  });

  // M1 (todo 5): transient-пульс кнопок назначения. animationend всплывает
  // до document; листенёр снимает [data-pulse] у любой кнопки. Под
  // prefers-reduced-motion токен вовсе не ставится (focusRail), поэтому
  // «зависший» атрибут с animation:none невозможен.
  document.addEventListener("animationend", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.hasAttribute("data-pulse")) {
      target.removeAttribute("data-pulse");
    }
  });

  function focusRail(slot: PairSlot): void {
    // M1: слот-клик pairbar НЕ мутирует пару; фокус — на первый ряд рейла
    // + пульс кнопок назначаемого слота (токен-ассерты, не тайминг).
    const rows = [...tbody.querySelectorAll<HTMLElement>("tr[data-rowkey]")];
    const first = rows[0];
    if (first === undefined) return;
    for (const item of rows) item.tabIndex = item === first ? 0 : -1;
    first.focus();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    for (const button of tbody.querySelectorAll<HTMLElement>(`[data-assign="${slot}"]`)) {
      button.setAttribute("data-pulse", "");
    }
  }

  return {
    root,
    focusRail,
    async reload(): Promise<void> {
      const page = await loadJoinedCatalog(opts.client);
      sessions = page.sessions;
      analyzedByDir = page.analyzedByDir;
      invalidByDir = page.invalidByDir;
      render();
    },
  };
}
