/** Shared inspect table: tokens via .lnt-table, cap long lists. */

import { el } from "../../../components/primitives/dom";

export const TABLE_ROW_CAP = 24;

export function renderTable(
  body: HTMLElement,
  headers: readonly string[],
  rows: readonly (readonly string[])[],
): void {
  if (rows.length > TABLE_ROW_CAP) {
    body.append(el("p", { className: "lnt-w1-panel-note", text: `rows ${String(rows.length)}` }));
  }
  const table = el("table", { className: "lnt-table" });
  const headRow = el("tr");
  for (const header of headers) headRow.append(el("th", { text: header }));
  const thead = el("thead");
  thead.append(headRow);
  const tbody = el("tbody");
  const shown = rows.length > TABLE_ROW_CAP ? rows.slice(0, TABLE_ROW_CAP) : rows;
  for (const row of shown) {
    const tr = el("tr");
    for (const cell of row) tr.append(el("td", { text: cell }));
    tbody.append(tr);
  }
  table.append(thead, tbody);
  body.append(table);
}
