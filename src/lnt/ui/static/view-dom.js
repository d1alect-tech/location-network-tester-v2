export function element(tagName, className, text) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

export function valueText(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function numberText(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "—";
}

export function appendTableHeader(table, labels) {
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  for (const label of labels) {
    const cell = element("th", "", label);
    cell.scope = "col";
    row.append(cell);
  }
  head.append(row);
  table.append(head);
}

export function appendDataCell(row, value, dataLabel = "") {
  const cell = element("td", "", value);
  if (dataLabel) cell.dataset.label = dataLabel;
  row.append(cell);
  return cell;
}
