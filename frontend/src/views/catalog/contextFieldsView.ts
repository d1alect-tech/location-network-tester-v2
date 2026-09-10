/** Таблица полей контекста V6 (.tbl) и панель восстановления (.banner).
 * Сигнатуры и контракт без изменений: значение с единицей, источник
 * и доступность по контракту ContextField бэкенда. */

import type { CollectionStatus, ContextField, FieldSource } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { reasonCodeExplanation } from "./catalogModel";

const SOURCE_LABELS: Record<FieldSource, string> = {
  automatic: "Автоматически",
  profile: "Из профиля",
  user: "Пользователь",
  derived: "Вычислено",
};

const STATUS_LABELS: Record<CollectionStatus, string> = {
  collected: "Собрано",
  unavailable: "Недоступно",
  not_collected: "Не собирается",
};

export function formatFieldValue(field: ContextField): string {
  const unit = field.unit ? ` ${field.unit}` : "";
  return `${String(field.value)}${unit}`;
}

export function createFieldsTable(fields: Record<string, ContextField>): HTMLElement {
  const table = el("table", { className: "tbl" });
  const head = el("tr", {}, [
    el("th", { attrs: { scope: "col" }, text: "Поле" }),
    el("th", { attrs: { scope: "col" }, text: "Значение" }),
    el("th", { attrs: { scope: "col" }, text: "Источник" }),
    el("th", { attrs: { scope: "col" }, text: "Доступность" }),
  ]);
  const body = el("tbody");
  for (const [key, field] of Object.entries(fields)) {
    const status = STATUS_LABELS[field.collection_status ?? "collected"];
    const row = el("tr", {}, [
      el("td", { className: "t-mono", text: key }),
      el("td", { className: "t-mono", text: formatFieldValue(field) }),
      el("td", { className: "t-compact", text: SOURCE_LABELS[field.source ?? "automatic"] }),
      el("td", {
        className: `t-compact${field.collection_status === "unavailable" ? " is-unavailable" : ""}`,
        text: `${status}${
          field.collection_reason ? ` — ${field.collection_reason}` : ""
        } · ${field.captured_at.slice(0, 19).replace("T", " ")}`,
      }),
    ]);
    body.append(row);
  }
  table.append(el("thead", {}, [head]), body);
  return table;
}

export function createRecoveryPanel(reasonCodes: string[], health: string): HTMLElement {
  const panel = el("div", {
    className: "banner lnt-cat-recovery",
    attrs: { role: "note", "aria-label": "Состояние контекста" },
  });
  const summary =
    health === "context_valid"
      ? "Контекст исправен. Журнал изменений содержит предупреждение."
      : health === "context_absent"
        ? "Контекст сессии ещё не сохранён. Поля ниже можно заполнить и сохранить."
        : health === "context_invalid"
          ? "Контекст сессии повреждён. Проблема относится только к контексту."
          : `Контекст требует внимания (${health}).`;
  panel.append(
    el("p", {
      className: "banner-title",
      text: summary,
    }),
  );
  if (reasonCodes.length > 0) {
    const list = el("ul", { className: "banner-list" });
    list.append(...reasonCodes.map((code) => el("li", { text: reasonCodeExplanation(code) })));
    panel.append(list);
  }
  return panel;
}
