/** Результат трендового запроса (todo 43): описательная сводка /trends/query —
 * сетка метаданных, средние по группам, маркировка descriptive_exploratory.
 * C1-лист, выделен из trendView.ts: тексты маркировок и ограничений
 * байт-в-байт, причинность исключена. V6-разметка зафиксированной волны
 * сохранена (.banner.banner-inline, .meter-grid, .kpi/.meter-label/.meter-value). */

import type { TrendAnalysisResult } from "../../api/types-research";
import { el } from "../../components/primitives/dom";

export function formatTrendValue(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(4) : "недоступно";
}

function qualityOf(result: TrendAnalysisResult): Record<string, unknown> | null {
  const raw = (result as Record<string, unknown>).data_quality;
  return typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : null;
}

function metaGrid(result: TrendAnalysisResult): HTMLElement {
  const meta = result.metadata;
  const grid = el("dl", { className: "lnt-exp-result-grid meter-grid" });
  const pairs: [string, string][] = [
    ["Единицы", meta.units],
    ["Рецепт (estimator)", `${meta.estimator} · описательный`],
    ["N пригодных наблюдений", String(meta.n)],
  ];
  const quality = qualityOf(result);
  if (quality) {
    pairs.push(
      ["Входных наблюдений", String(quality.input_count ?? "недоступно")],
      ["Пропусков времени", String(quality.missing_timestamp_count ?? "недоступно")],
      [
        "Дубликатов (политика)",
        `${String(quality.duplicate_count ?? "недоступно")} · ${String(quality.dedupe_policy ?? "—")}`,
      ],
    );
  }
  for (const [term, definition] of pairs) {
    grid.append(
      el("div", { className: "kpi" }, [
        el("dt", { className: "meter-label", text: term }),
        el("dd", { className: "meter-value t-mono", text: definition }),
      ]),
    );
  }
  return grid;
}

function groupMeans(result: TrendAnalysisResult): HTMLElement {
  const list = el("ul", {
    className: "lnt-exp-limitations",
    attrs: { "aria-label": "Групповые средние" },
  });
  const trendsRaw = (result as Record<string, unknown>).trends;
  if (!Array.isArray(trendsRaw)) return list;
  for (const trend of trendsRaw) {
    if (typeof trend !== "object" || trend === null) continue;
    const row = trend as Record<string, unknown>;
    list.append(
      el("li", {
        text: `${String(row.group_dimension ?? "группа")}=${String(row.group_value ?? "—")}: N=${String(row.n ?? "?")}, среднее ${formatTrendValue(row.mean as number | null)} ${result.metadata.units} (описательное, exploratory)`,
      }),
    );
  }
  return list;
}

/** Узлы результата в порядке волны: баннер, сетка, заголовок, средние,
 * панель смешивающих факторов, маркировка. */
export function renderTrendResult(
  result: TrendAnalysisResult,
  minimumN: number,
  confound: HTMLElement,
): HTMLElement[] {
  const meta = result.metadata;
  const limited = meta.n < Math.max(minimumN, 5);
  const banner = el("p", {
    className: `lnt-exp-banner ${limited ? "lnt-exp-banner-warn" : "lnt-exp-banner-info"} banner banner-inline`,
    attrs: { role: "status" },
    text: limited
      ? "Мало данных: результат ограничен, интерпретация неустойчива."
      : "Достаточно данных для описательной сводки.",
  });
  return [
    banner,
    metaGrid(result),
    el("h3", { className: "lnt-exp-subtitle", text: "Средние по группам (описательные)" }),
    groupMeans(result),
    confound,
    renderTrendLimitations(meta),
  ];
}

/** Маркировка результата: exploratory, единицы, N, запрет вымысла. */
export function renderTrendLimitations(meta: TrendAnalysisResult["metadata"]): HTMLElement {
  return el("div", { className: "lnt-exp-provenance" }, [
    el("h4", { className: "lnt-exp-provenance-title", text: "Маркировка результата" }),
    el("p", {
      className: "lnt-exp-meta-line",
      text: `Описательный разведочный анализ (exploratory). Единицы: ${meta.units} · N=${String(meta.n)}. Ранговые связи — корреляции, НЕ причинные эффекты.`,
    }),
    el("p", {
      className: "lnt-exp-meta-line",
      text: "Недостающие данные показаны как «недоступно» с кодом причины и никогда не восполняются вымыслом.",
    }),
  ]);
}
