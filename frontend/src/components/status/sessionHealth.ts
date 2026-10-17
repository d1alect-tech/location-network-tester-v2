/** ЕДИНЫЙ словарь здоровья сессий (ui-refactor-3, задача 4 — hoist D1g).
 *
 * Один источник русских подписей health-кодов и тонов бейджа для каталога
 * (views/catalog) и рейла инспекции (views/inspect): до этого жили три
 * диалекта — HEALTH_LABELS каталога, глиф-карта HEALTH_GLYPH парбара и
 * тоновые глифы пилюль. Каталог и рейл рисуют ТОТ ЖЕ узел пилюли.
 *
 * Analyzed-измерение НЕ часть health: health-эндпоинт возвращает «ok» при
 * отсутствии metrics.json (reconcile_parse.py:55-58), поэтому analyzed идёт
 * только из JOIN(legacySessions, health) — см. catalogJoinedSource.ts. */

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

/** Тон → глиф пилюли: та же тройка, что рисовал каталог. */
const GLYPH_BY_TONE: Readonly<Record<string, string>> = {
  ok: "●",
  warn: "▲",
  error: "✕",
};

export function glyphForTone(tone: string): string {
  return GLYPH_BY_TONE[tone] ?? "●";
}

/** Фразы analyzed-измерения: только из JOIN, никогда из health-кода. */
export const ANALYZED_LABEL = "Проанализирована";
export const UNANALYZED_LABEL = "Не проанализирована";
