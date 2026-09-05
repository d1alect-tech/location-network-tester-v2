/** Поля формы профилей (C2-лист, сменил T11-модуль profileFormView):
 * динамические контролы под вид профиля и заполнение формы данными
 * существующей revision. Имена полей — контракт data каждого вида,
 * без изменений. Сборка типизированного запроса — profileForms.collectProfileData. */

import type { ProfileData, ProfileKind } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";

export function input(name: string, label: string, value = ""): HTMLElement {
  const control = document.createElement("input");
  control.type = "text";
  control.name = name;
  control.className = "lnt-input";
  if (value !== "") control.value = value;
  return createField({ label, control }).root;
}

export function quantityInputs(prefix: string, label: string): HTMLElement {
  const wrap = el("div", { className: "lnt-cat-quantity" });
  wrap.append(
    input(`${prefix}_value`, `${label} — значение`),
    input(`${prefix}_unit`, `${label} — единица`),
  );
  return wrap;
}

function conditionsFields(): HTMLElement[] {
  const select = document.createElement("select");
  select.name = "damper_state";
  select.className = "lnt-select";
  for (const [value, labelText] of [
    ["unknown", "Неизвестно"],
    ["on", "Включён"],
    ["off", "Выключен"],
  ] as const) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labelText;
    select.append(option);
  }
  return [
    createField({ label: "Демпфер", control: select }).root,
    input("nearby_load_states", "Нагрузки рядом (через запятую)"),
  ];
}

/** Динамические поля формы под вид профиля (контракт data каждого вида). */
export function formFieldsFor(kind: ProfileKind): HTMLElement[] {
  switch (kind) {
    case "location":
      return [
        input("alias", "Псевдоним локации"),
        input("outlet", "Розетка"),
        input("circuit", "Автомат/цепь"),
      ];
    case "equipment":
      return [input("alias", "Псевдоним оборудования"), input("model", "Модель")];
    case "front_end":
      return [
        quantityInputs("resistance", "Сопротивление"),
        quantityInputs("c1", "C1"),
        quantityInputs("c2", "C2"),
      ];
    case "transformer":
      return [
        quantityInputs("primary", "Первичная обмотка"),
        quantityInputs("secondary", "Вторичная обмотка"),
      ];
    case "conditions":
      return conditionsFields();
  }
}

/** Заливка существующих значений revision в поля формы по name. */
export function fillExisting(host: HTMLElement, data: ProfileData): void {
  const flat: Record<string, string> = {};
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === "string") flat[key] = value;
    else if (value && typeof value === "object" && "value" in value && "unit" in value) {
      flat[`${key}_value`] = String(value.value);
      flat[`${key}_unit`] = String(value.unit);
    }
  }
  for (const [name, value] of Object.entries(flat)) {
    const node = host.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`);
    if (node) node.value = value;
  }
  if ("nearby_load_states" in data && Array.isArray(data.nearby_load_states)) {
    const node = host.querySelector<HTMLInputElement>('[name="nearby_load_states"]');
    if (node) node.value = data.nearby_load_states.join(", ");
  }
}
