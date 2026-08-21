/** Формы профилей: сборка типизированного запроса по виду профиля.
 * Значения величин строго положительные числа с единицей (контракт
 * QuantityData); некорректный ввод возвращает русское сообщение об ошибке,
 * а не тихо отправляется на сервер. */

import type {
  ConditionsData,
  EquipmentData,
  FrontEndData,
  LocationData,
  ProfileData,
  ProfileKind,
  TransformerData,
} from "../../api/types";

export interface ProfileFormResult {
  data: ProfileData;
}

export const PROFILE_KIND_LABELS: Record<ProfileKind, string> = {
  location: "Локация",
  equipment: "Оборудование",
  front_end: "Фронтенд входа",
  transformer: "Трансформатор",
  conditions: "Условия измерения",
};

/** Читает текстовое поле формы; пустое значение → ошибка с русской подписью. */
function requireText(value: string, label: string): string {
  const trimmed = value.trim();
  if (trimmed === "") throw new Error(`Заполните поле «${label}».`);
  return trimmed;
}

function parseQuantity(
  valueText: string,
  unitText: string,
  label: string,
): { value: number; unit: string } {
  const parsed = Number(valueText.replace(",", "."));
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`«${label}»: введите положительное число.`);
  }
  return { value: parsed, unit: requireText(unitText, `${label} (единица)`) };
}

/** Собирает данные профиля из DOM-формы; бросает Error с русским текстом. */
export function collectProfileData(kind: ProfileKind, form: HTMLFormElement): ProfileFormResult {
  const read = (name: string): string =>
    form.elements.namedItem(name) instanceof HTMLInputElement ||
    form.elements.namedItem(name) instanceof HTMLSelectElement
      ? (form.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement).value
      : "";
  switch (kind) {
    case "location": {
      const data: LocationData = {
        alias: requireText(read("alias"), "Псевдоним локации"),
        outlet: requireText(read("outlet"), "Розетка"),
        circuit: requireText(read("circuit"), "Автомат/цепь"),
      };
      return { data };
    }
    case "equipment": {
      const data: EquipmentData = {
        alias: requireText(read("alias"), "Псевдоним оборудования"),
        model: requireText(read("model"), "Модель"),
      };
      return { data };
    }
    case "front_end": {
      const data: FrontEndData = {
        resistance: parseQuantity(
          read("resistance_value"),
          read("resistance_unit"),
          "Сопротивление",
        ),
        c1: parseQuantity(read("c1_value"), read("c1_unit"), "C1"),
        c2: parseQuantity(read("c2_value"), read("c2_unit"), "C2"),
      };
      return { data };
    }
    case "transformer": {
      const data: TransformerData = {
        nominal_primary: parseQuantity(
          read("primary_value"),
          read("primary_unit"),
          "Первичная обмотка",
        ),
        nominal_secondary: parseQuantity(
          read("secondary_value"),
          read("secondary_unit"),
          "Вторичная обмотка",
        ),
      };
      return { data };
    }
    case "conditions": {
      const damper = read("damper_state");
      const states = read("nearby_load_states")
        .split(",")
        .map((part) => part.trim())
        .filter((part) => part !== "");
      const data: ConditionsData = {
        damper_state: damper === "on" || damper === "off" ? damper : "unknown",
        nearby_load_states: states,
      };
      return { data };
    }
  }
}
