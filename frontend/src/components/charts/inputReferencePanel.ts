/** Панель «Приведение ко входу» (todo 41, волна C2): статус/причина/модель
 * из metrics.json v2. Выделено из workbench.ts без изменений; зависит только
 * от формы metrics.json v2, не от workbench.ts. */

import { el } from "../primitives/dom";

export function renderInputReference(host: HTMLElement, source: unknown): void {
  host.replaceChildren();
  const info =
    typeof source === "object" && source !== null ? (source as Record<string, unknown>) : null;
  if (info === null) {
    host.append(
      el("p", { className: "lnt-helper-text", text: "Приведение ко входу: нет данных анализа." }),
    );
    return;
  }
  const available = info.status === "available";
  const reason = typeof info.reason_code === "string" ? ` (${info.reason_code})` : "";
  const summary = el("p", {
    className: "lnt-input-ref-status",
    text: available
      ? `Спектр приведён ко входу · модель ${String(info.model_kind ?? "—")}`
      : `Спектр не приведён ко входу${reason}`,
  });
  const bins =
    typeof info.qualified_bin_count === "number" && typeof info.total_bin_count === "number"
      ? `Квалифицировано бинов: ${info.qualified_bin_count} из ${info.total_bin_count}`
      : "Квалификация бинов недоступна";
  host.append(summary, el("p", { className: "lnt-helper-text", text: bins }));
}
