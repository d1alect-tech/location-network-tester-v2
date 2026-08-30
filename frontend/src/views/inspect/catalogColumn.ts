import type { CatalogQuery, CatalogSession } from "../../api/types";
import { clearElement, el } from "../../components/primitives/dom";
import { buildCatalogRows, type CatalogSort, type SortDir } from "./catalogColumnModel";
import { renderCatalogRow } from "./catalogColumnRender";
import type { PairStateHandle } from "./pairState";

export interface CatalogColumnClient {
  catalogSessions(
    query?: CatalogQuery,
    options?: unknown,
  ): Promise<{ readonly items: readonly CatalogSession[] }>;
}

export interface CatalogColumnOptions {
  readonly client: CatalogColumnClient;
  readonly pair: PairStateHandle;
  readonly onPick: (sessionId: string) => void;
}

export interface CatalogColumnHandle {
  readonly root: HTMLElement;
  reload(): Promise<void>;
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

  const found = el("span", { className: "cat-found", attrs: { "data-cat-found": "" } });
  const search = el("input", {
    className: "cat-search",
    attrs: {
      type: "search",
      "data-cat-search": "",
      "aria-label": "Поиск по метке",
    },
  });
  const clear = el("button", {
    attrs: { type: "button", "data-cat-clear": "" },
    text: "Сбросить",
  });

  const labelBtn = el("button", {
    className: "cat-sort",
    text: "Метка",
    attrs: { type: "button", "data-cat-sort": "label" },
  });
  const dateBtn = el("button", {
    className: "cat-sort",
    text: "Дата",
    attrs: { type: "button", "data-cat-sort": "date" },
  });
  const labelTh = el("th", { attrs: { scope: "col" } }, [labelBtn]);
  const dateTh = el("th", { attrs: { scope: "col" } }, [dateBtn]);
  const tbody = el("tbody");
  const table = el("table", { className: "tbl tbl-cat" }, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", { attrs: { scope: "col" } }),
        labelTh,
        el("th", { attrs: { scope: "col" }, text: "Тип" }),
        dateTh,
      ]),
    ]),
    tbody,
  ]);

  const root = el("section", { className: "panel" }, [
    el("div", { className: "panel-hd" }, [el("h2", { className: "panel-title", text: "Каталог" }), found]),
    el("div", { className: "cat-tools" }, [search, clear]),
    table,
  ]);

  function syncAriaSort(): void {
    switch (sort) {
      case "label":
        labelTh.setAttribute("aria-sort", ariaSortValue(dir));
        dateTh.setAttribute("aria-sort", "none");
        return;
      case "date":
        dateTh.setAttribute("aria-sort", ariaSortValue(dir));
        labelTh.setAttribute("aria-sort", "none");
        return;
      default:
        return assertNever(sort);
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
        renderCatalogRow(row, { grouped: sort === "date", pair, onPick: opts.onPick }),
      );
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

  return {
    root,
    async reload(): Promise<void> {
      const page = await opts.client.catalogSessions({ page_size: 200 });
      sessions = page.items;
      render();
    },
  };
}
