/** Модель рабочей области каталога: русские подписи health, соответствие
 * параметров URL (routeState) и query-контракта GET /api/catalog/sessions.
 * Терминология DESIGN.md: «папка» — группировка, «идентификатор сессии» — id,
 * «метка» — label, «профиль» — profile. Эти понятия не смешиваются. */

import type { SessionHealth } from "../../api/types";

/** Русские подписи health-кодов с тоном бейджа (не только цвет). */
export const HEALTH_LABELS: Record<
  SessionHealth,
  { label: string; tone: "ok" | "warn" | "error" }
> = {
  ok: { label: "Исправна", tone: "ok" },
  corrupt_manifest: { label: "Повреждён манифест", tone: "error" },
  missing_files: { label: "Нет файлов", tone: "error" },
  partial: { label: "Частичная", tone: "warn" },
  duplicate_id: { label: "Дубль идентификатора", tone: "warn" },
  context_invalid: { label: "Контекст повреждён", tone: "error" },
  analysis_invalid: { label: "Анализ некорректен", tone: "error" },
};

export const SESSION_TYPE_LABELS: Record<string, string> = {
  capture: "Захват",
  simulate: "Симуляция",
  line_quality: "Качество сети",
};

export function sessionTypeLabel(value: string): string {
  return SESSION_TYPE_LABELS[value] ?? value;
}

/** Параметры фильтров, поддерживаемые серверным контрактом CatalogQuery. */
export const FILTER_PARAMS = [
  "health",
  "label",
  "session_type",
  "created_from",
  "created_to",
  "profile",
  "tag",
] as const;

export type FilterParam = (typeof FILTER_PARAMS)[number];

/** Фильтры рабочей области в порядке панели. */
export type FilterValues = Partial<Record<FilterParam, string>>;

/** Читает только известные параметры фильтров из параметров маршрута. */
export function filtersFromParams(params: Record<string, string>): FilterValues {
  const result: FilterValues = {};
  for (const key of FILTER_PARAMS) {
    const value = params[key];
    if (value) result[key] = value;
  }
  return result;
}

/** Полные параметры маршрута для навигации (только непустые значения). */
export function paramsFromFilters(filters: FilterValues): Record<string, string> {
  const result: Record<string, string> = {};
  for (const key of FILTER_PARAMS) {
    const value = filters[key];
    if (value) result[key] = value;
  }
  return result;
}

/** Есть ли хоть один активный фильтр. */
export function hasActiveFilters(filters: FilterValues): boolean {
  return Object.values(filters).some((value) => value !== undefined && value !== "");
}

/** Считает совпадения подстроки поиска без учёта регистра. */
export function matchesTextFilter(filters: FilterValues): boolean {
  return Boolean(filters.label);
}

/** Русское объяснение кода причины из reason_codes контекста. */
export function reasonCodeExplanation(code: string): string {
  if (code === "context_events_torn_tail") {
    return "Журнал изменений контекста оборван в конце; загружена последняя целая версия контекста.";
  }
  if (code === "context_cache_malformed") {
    return "Не удалось прочитать context.json — файл контекста повреждён.";
  }
  if (code === "context_identity_mismatch") {
    return "Идентификатор в context.json не совпадает с открытой сессией.";
  }
  return `Причина: ${code}`;
}
