/** Контролы workbench (todo 41, волна C2): CSV-хелперы, поле с меткой,
 * кнопка скачивания, наполнение селектов каталога. Выделено из workbench.ts
 * без изменений поведения; зависит только от DOM-примитивов и типа каталога. */

import type { CatalogPage } from "../../api/types";
import { el } from "../primitives/dom";

export function csvOf(headers: string[], x: readonly number[], y: readonly number[]): string {
  const rows: string[] = [];
  const count = Math.min(x.length, y.length);
  for (let i = 0; i < count; i += 1) {
    const xi = x[i];
    const yi = y[i];
    if (xi !== undefined && yi !== undefined) rows.push(`${xi},${yi}`);
  }
  return [headers.join(","), ...rows].join("\n");
}

export function labeled(label: string, control: HTMLElement): HTMLElement {
  return el("label", { className: "lnt-field-inline" }, [
    el("span", { className: "lnt-label-text", text: label }),
    control,
  ]);
}

export function csvButton(onClick: () => void): HTMLElement {
  const button = el("button", {
    className: "lnt-btn lnt-btn-small",
    text: "Скачать CSV",
    attrs: { type: "button" },
  });
  button.addEventListener("click", onClick);
  return button;
}

export function fillSessions(
  select: HTMLSelectElement,
  page: CatalogPage | null,
  placeholder: string,
): void {
  select.replaceChildren(el("option", { text: placeholder, attrs: { value: "" } }));
  if (page === null) return;
  for (const session of page.items) {
    const title = session.label === null ? session.id : `${session.id} · ${session.label}`;
    select.append(el("option", { text: title, attrs: { value: session.id } }));
  }
}
