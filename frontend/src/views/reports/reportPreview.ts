/** DOM-сборка превью отчёта: provenance, единицы/N, результат, плоскости,
 * рецепты, ограничения. Чистое построение узлов без состояния и сети —
 * рабочая область только вставляет результат в detailHost. */

import { el } from "../../components/primitives/dom";
import type { ReportDraft } from "./reportModel";
import { formatMetric } from "./reportModel";

function definitionList(rows: [string, string][]): HTMLElement {
  const list = el("dl", { className: "lnt-rep-grid" });
  for (const [term, value] of rows) {
    list.append(el("dt", { text: term }), el("dd", { className: "lnt-rep-mono", text: value }));
  }
  return list;
}

function outcomeBlock(draft: ReportDraft): HTMLElement {
  const host = el("div", { className: "lnt-rep-outcome" });
  const outcome = draft.outcome;
  if (outcome.kind === "refusal") {
    host.append(
      el("p", {
        className: "lnt-rep-banner lnt-rep-banner-warn",
        attrs: { role: "alert" },
        text: `Расчёт заблокирован бэкендом. Точная причина: ${outcome.reason_code}. Числовые эффекты не выдаются.`,
      }),
    );
    return host;
  }
  const rows: [string, string][] = [
    ["Средний эффект", formatMetric(outcome.effect.mean_effect)],
    ["Медианный эффект", formatMetric(outcome.effect.median_effect)],
    ["Робастный эффект", formatMetric(outcome.effect.robust_effect)],
  ];
  if (outcome.effect.interval_low !== null && outcome.effect.interval_high !== null) {
    rows.push([
      `Интервал (${formatMetric(outcome.effect.confidence_level ?? 0.95)})`,
      `[${formatMetric(outcome.effect.interval_low)}; ${formatMetric(outcome.effect.interval_high)}] ${draft.core.units}`,
    ]);
  }
  if (outcome.kind === "effect" && outcome.drift !== null) {
    rows.push(["Дрейф A (A2−A1), среднее", formatMetric(outcome.drift.mean_effect)]);
  }
  if (outcome.kind === "descriptive") {
    host.append(
      el("p", {
        className: "lnt-rep-banner lnt-rep-banner-info",
        text: "Описательная оценка без доверительного интервала: не является статистической уверенностью.",
      }),
    );
  }
  host.append(definitionList(rows));
  return host;
}

export function previewBlock(draft: ReportDraft): HTMLElement {
  const planes = el("ul", {
    className: "lnt-rep-planes",
    attrs: { "aria-label": "Плоскости измерения" },
  });
  for (const plane of draft.planes) {
    planes.append(
      el("li", {
        text: plane.available
          ? `${plane.session_id}: приведён ко входу (${plane.model_kind ?? "модель"})`
          : `${plane.session_id}: недоступно (${plane.reason_code ?? "причина неизвестна"})`,
      }),
    );
  }
  if (draft.planes.length === 0) {
    planes.append(el("li", { text: "Данные о плоскостях измерения недоступны." }));
  }
  const recipes = el("ul", {
    className: "lnt-rep-recipes",
    attrs: { "aria-label": "Рецепты анализа" },
  });
  for (const recipe of draft.recipes) {
    recipes.append(el("li", { text: `${recipe.name} (${recipe.recipe_id})` }));
  }
  if (draft.recipes.length === 0) {
    recipes.append(el("li", { text: "Рецепты анализа не зарегистрированы." }));
  }
  const limitations = el("ul", {
    className: "lnt-rep-limitations",
    attrs: { "aria-label": "Ограничения отчёта" },
  });
  for (const limitation of draft.limitations) {
    limitations.append(el("li", { text: `${limitation.code}: ${limitation.detail}` }));
  }
  if (draft.limitations.length === 0) {
    limitations.append(el("li", { text: "Не обнаружены." }));
  }
  return el("div", { className: "lnt-rep-preview" }, [
    el("h3", { className: "lnt-exp-subtitle", text: "Происхождение (provenance)" }),
    definitionList([
      [
        "Эксперимент",
        `${draft.provenance.experiment_id} (ревизия ${String(draft.provenance.experiment_revision)})`,
      ],
      ["Оцениваемый признак", draft.provenance.estimand],
      ["Задача расчёта", draft.provenance.job_id],
      ["Собран", draft.provenance.generated_at],
    ]),
    el("h3", { className: "lnt-exp-subtitle", text: "Единицы и объём выборки" }),
    definitionList([
      ["Единицы", draft.core.units],
      ["N", `${String(draft.core.n)} (${draft.core.sampling_unit})`],
      ["Иерархия", draft.core.hierarchy.join(" → ") || "—"],
      ["Пропущено значений", String(draft.core.missing_count)],
      ["Оценщик", draft.core.estimator],
      ["Метод интервала", draft.core.interval_method],
    ]),
    el("h3", { className: "lnt-exp-subtitle", text: "Результат" }),
    outcomeBlock(draft),
    el("h3", { className: "lnt-exp-subtitle", text: "Плоскости измерения" }),
    planes,
    el("h3", { className: "lnt-exp-subtitle", text: "Рецепты анализа" }),
    recipes,
    el("h3", { className: "lnt-exp-subtitle", text: "Ограничения" }),
    limitations,
  ]);
}
