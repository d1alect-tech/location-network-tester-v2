// Honest CH1 plane provenance for the session analysis view.
//
// The spectrum shown in the UI is the raw scope-plane PSD of CH1; it is never
// presented as corrected input-referred data, and no corrected-plane selector
// is offered. The machine-readable `metrics.json.ch1_input_reference` status is
// surfaced verbatim when present. All values are written through textContent, so
// hostile manifest strings can only ever render as inert text.

const SCOPE_PLANE_NOTE =
  "Спектр — сырой scope-plane PSD канала CH1; он не приведён ко входу.";

function asText(value) {
  return value === null || value === undefined || value === "" ? "н/д" : String(value);
}

function countText(value) {
  return Number.isFinite(Number(value)) ? String(value) : "н/д";
}

function referenceRows(reference) {
  if (reference.status === "available") {
    return [
      ["Статус", "Доступно"],
      ["Модель", asText(reference.model_kind)],
      [
        "Квалифицировано полос",
        `${countText(reference.qualified_bin_count)}/${countText(reference.total_bin_count)}`,
      ],
    ];
  }
  if (reference.status === "unavailable") {
    return [["Статус", "Недоступно"], ["Причина", asText(reference.reason_code)]];
  }
  return [["Статус", asText(reference.status)], ["Причина", asText(reference.reason_code)]];
}

function textNode(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function referenceBlock(reference, doc) {
  const box = textNode(doc, "div", "ch1-input-reference");
  const list = textNode(doc, "dl", "manifest-grid");
  for (const [term, value] of referenceRows(reference)) {
    const item = doc.createElement("div");
    item.append(textNode(doc, "dt", "", term), textNode(doc, "dd", "", value));
    list.append(item);
  }
  box.append(textNode(doc, "h3", "", "Приведение ко входу CH1"), list);
  return box;
}

export function renderCh1Section(analysis, doc = document) {
  const section = textNode(doc, "div", "ch1-section");
  section.append(textNode(doc, "p", "helper-text spectrum-plane-note", SCOPE_PLANE_NOTE));
  const reference = analysis?.ch1_input_reference;
  if (reference) section.append(referenceBlock(reference, doc));
  return section;
}
