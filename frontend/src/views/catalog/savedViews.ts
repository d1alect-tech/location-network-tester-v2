/** Сохранённые представления каталога: именованные наборы фильтров,
 * персистентные в localStorage. Повреждённые записи отбрасываются,
 * а не ломают панель. Имя представления — пользовательский текст. */

import type { FilterParam } from "./catalogModel";

const STORAGE_KEY = "lnt.catalog.savedViews.v1";
export const MAX_SAVED_VIEWS = 20;

export interface SavedView {
  name: string;
  filters: Partial<Record<FilterParam, string>>;
}

function isFilterRecord(value: unknown): value is Partial<Record<FilterParam, string>> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return Object.entries(value).every(
    ([key, entry]) => typeof key === "string" && (entry === undefined || typeof entry === "string"),
  );
}

/** Разбирает сохранённые представления; некорректный JSON → пустой список. */
export function parseSavedViews(raw: string | null): SavedView[] {
  if (raw === null) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  const result: SavedView[] = [];
  for (const item of parsed) {
    if (typeof item !== "object" || item === null) continue;
    const record = item as Record<string, unknown>;
    if (typeof record.name !== "string" || record.name === "") continue;
    if (!isFilterRecord(record.filters)) continue;
    result.push({ name: record.name, filters: record.filters });
  }
  return result.slice(0, MAX_SAVED_VIEWS);
}

export function loadSavedViews(storage: Storage): SavedView[] {
  let raw: string | null = null;
  try {
    raw = storage.getItem(STORAGE_KEY);
  } catch {
    return []; // приватный режим / недоступный storage — работаем без сохранений
  }
  return parseSavedViews(raw);
}

export function saveSavedViews(storage: Storage, views: SavedView[]): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(views.slice(0, MAX_SAVED_VIEWS)));
  } catch {
    // переполнение квоты не должно ронять UI: представление просто не сохранится
  }
}
