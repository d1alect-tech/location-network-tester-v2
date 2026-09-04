/** DOM-сборка превью отчёта: стек V6-панелей (kit.css §5.2).
 * provenance/core — .meter-grid, результат — .readout-grid, плоскости/рецепты/
 * ограничения — ul.t-mono, текст выгрузки — pre.md. Легаси-классы lnt-rep-*
 * сохранены рядом для e2e reports.spec.ts. Чистое построение узлов без
 * состояния и сети — рабочая область только вставляет результат в detailHost.
 * Модель (reportModel.ts) не трогаем — только читаем. */

import { el } from "../../components/primitives/dom";
import type { ReportDraft } from "./reportModel";
import { composeReportMarkdown, formatMetric } from "./reportModel";

function panel(title: string, bodies: Node[], extraClass = ""): HTMLElement {
  const cls = extraClass ? `panel ${extraClass}` : "panel";
  return el("section", { className: cls }, [
    el("div", { className: "panel-hd" }, [el("h2", { className: "panel-title", text: title })]),
    /* Прокручиваемая область без интерактивных потомков: tabindex делает её
     * доступной клавиатуре (axe scrollable-region-focusable). */
    el("div", { className: "panel-bd", attrs: { tabindex: "0" } }, bodies),
  ]);
}

function meterGrid(rows: [string, string][]): HTMLElement {
  const grid = el("div", { className: "meter-grid lnt-rep-grid" });
  for (const [label, value] of rows) {
    grid.append(
      el("div", { className: "meter" }, [
        el("span", { className: "meter-label", text: label }),
        el("span", { className: "meter-value t-mono", text: value }),
      ]),
    );
  }
  return grid;
}

function readoutGrid(rows: [string, string][]): HTMLElement {
  const grid = el("div", { className: "readout-grid" });
  for (const [label, value] of rows) {
    grid.append(
      el("div", { className: "readout-cell" }, [
        el("span", { className: "readout-label", text: label }),
        el("span", { className: "readout-value t-mono", text: value }),
      ]),
    );
  }
  return grid;
}

function outcomeBlock(draft: ReportDraft): HTMLElement {
  const host = el("div", { className: "lnt-rep-outcome" });
  const outcome = draft.outcome;
  if (outcome.kind === "refusal") {
    host.append(
      el(
        "div",
        {
          className: "banner lnt-rep-banner lnt-rep-banner-warn",
          attrs: { role: "alert" },
        },
        [
          el("h3", { className: "banner-title", text: "Расчёт заблокирован бэкендом" }),
          el("p", {
            className: "banner-msg",
            text: `Точная причина: ${outcome.reason_code}. Числовые эффекты не выдаются.`,
          }),
        ],
      ),
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
      el(
        "div",
        {
          className: "banner lnt-rep-banner lnt-rep-banner-info",
          attrs: { role: "status" },
        },
        [
          el("p", {
            className: "banner-msg",
            text: "Описательная оценка без доверительного интервала: не является статистической уверенностью.",
          }),
        ],
      ),
    );
  }
  host.append(readoutGrid(rows));
  return host;
}

export function previewBlock(draft: ReportDraft): HTMLElement {
  const planes = el("ul", {
    className: "lnt-rep-planes t-mono",
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
    className: "lnt-rep-recipes t-mono",
    attrs: { "aria-label": "Рецепты анализа" },
  });
  for (const recipe of draft.recipes) {
    recipes.append(el("li", { text: `${recipe.name} (${recipe.recipe_id})` }));
  }
  if (draft.recipes.length === 0) {
    recipes.append(el("li", { text: "Рецепты анализа не зарегистрированы." }));
  }
  const limitations = el("ul", {
    className: "lnt-rep-limitations t-mono",
    attrs: { "aria-label": "Ограничения отчёта" },
  });
  for (const limitation of draft.limitations) {
    limitations.append(el("li", { text: `${limitation.code}: ${limitation.detail}` }));
  }
  if (draft.limitations.length === 0) {
    limitations.append(el("li", { text: "Не обнаружены." }));
  }
  const markdown = composeReportMarkdown(draft);
  const mdPanel = panel("Текст выгрузки (.md)", [
    el("pre", {
      className: "md t-mono",
      text: markdown,
      attrs: { tabindex: "0", "aria-label": "Текст выгрузки отчёта в формате Markdown" },
    }),
  ]);
  mdPanel.append(
    el("div", { className: "panel-ft" }, [
      el("p", {
        className: "t-compact",
        text: `Файл report-${draft.provenance.experiment_id}.md формируется клиентом из тех же данных, что показаны выше.`,
      }),
    ]),
  );
  return el("div", { className: "lnt-rep-preview" }, [
    panel("Происхождение (provenance)", [
      meterGrid([
        [
          "Эксперимент",
          `${draft.provenance.experiment_id} (ревизия ${String(draft.provenance.experiment_revision)})`,
        ],
        ["Оцениваемый признак", draft.provenance.estimand],
        ["Задача расчёта", draft.provenance.job_id],
        ["Собран", draft.provenance.generated_at],
      ]),
    ]),
    panel("Единицы и объём выборки", [
      meterGrid([
        ["Единицы", draft.core.units],
        ["N", `${String(draft.core.n)} (${draft.core.sampling_unit})`],
        ["Иерархия", draft.core.hierarchy.join(" → ") || "—"],
        ["Пропущено значений", String(draft.core.missing_count)],
        ["Оценщик", draft.core.estimator],
        ["Метод интервала", draft.core.interval_method],
      ]),
    ]),
    panel("Результат", [outcomeBlock(draft)]),
    panel("Плоскости измерения", [planes]),
    panel("Рецепты анализа", [recipes]),
    panel("Ограничения", [limitations]),
    mdPanel,
  ]);
}
