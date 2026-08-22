/** Панель результата с обязательной маркировкой (todo 43, требование плана):
 * единицы, N, рецепт (estimator + interval_method), плоскость
 * (scope/input-referred), ограничения; описательный vs инференциальный
 * статус явно. Причинных формулировок нет никогда. */

import type { StatisticsMetadata } from "../../api/types-research";
import { el } from "../../components/primitives/dom";

export interface EffectView {
  mean: number;
  median: number;
  robust: number;
  intervalLow: number | null;
  intervalHigh: number | null;
}

export interface ResultPanelInput {
  title: string;
  effect: EffectView | null;
  metadata: StatisticsMetadata;
  /** refusal-результат A/B/A: эффект заблокирован дрейфом A. */
  refusalReason?: string | null;
  drift?: EffectView | null;
  limitationsExtra?: string[];
}

const PLANE_NOTE =
  "Плоскость данных: scope-plane значения из метрик сессий; приведение ко входу не применяется и не выдаётся за input-referred.";

function fmt(value: number): string {
  return Number.isFinite(value) ? value.toFixed(4) : "недоступно";
}

export function renderResultPanel(input: ResultPanelInput): HTMLElement {
  const root = el("section", { className: "lnt-exp-result" });
  root.append(el("h3", { className: "lnt-exp-subtitle", text: input.title }));

  // Квалифицирующий статус: инференциальный или описательный.
  const inferential = input.effect?.intervalLow !== null && input.effect?.intervalLow !== undefined;
  const statusBadge = el(
    "p",
    {
      className: `lnt-exp-result-status ${inferential ? "lnt-exp-status-inferential" : "lnt-exp-status-descriptive"}`,
      attrs: { role: "status" },
    },
    [
      el("strong", {
        text: inferential
          ? "Инференциальная оценка (интервал доступен)"
          : "Описательная оценка без интервала",
      }),
    ],
  );
  root.append(statusBadge);

  if (input.refusalReason) {
    root.append(
      el("p", {
        className: "lnt-exp-banner lnt-exp-banner-warn",
        text: `Контраст заблокирован: дрейф A превышает порог (${input.refusalReason}). Числовой контраст не вычисляется.`,
      }),
    );
  }

  if (input.effect === null) {
    root.append(
      el("p", {
        className: "lnt-exp-banner lnt-exp-banner-info",
        text: "Числовая оценка недоступна: недостаточно данных для расчёта.",
      }),
    );
  } else {
    const grid = el("dl", { className: "lnt-exp-result-grid" });
    const rows: [string, string][] = [
      ["Средний эффект (B−A)", `${fmt(input.effect.mean)} ${input.metadata.units}`],
      ["Медианный эффект", `${fmt(input.effect.median)} ${input.metadata.units}`],
      ["Устойчивая оценка (20% trimmed)", `${fmt(input.effect.robust)} ${input.metadata.units}`],
    ];
    if (inferential) {
      rows.push([
        "95% интервал (bootstrap)",
        `[${fmt(input.effect.intervalLow ?? Number.NaN)}; ${fmt(input.effect.intervalHigh ?? Number.NaN)}] ${input.metadata.units}`,
      ]);
    }
    for (const [term, definition] of rows) {
      grid.append(el("dt", { text: term }), el("dd", { text: definition }));
    }
    root.append(grid);

    if (input.drift !== null && input.drift !== undefined) {
      root.append(
        el("p", {
          className: "lnt-exp-drift-note",
          text: `Дрейф A (A2−A1), отдельно от контраста: среднее ${fmt(input.drift.mean)} ${input.metadata.units}. Дрейф не интерпретируется причинно.`,
        }),
      );
    }
  }

  root.append(renderProvenance(input));
  return root;
}

function renderProvenance(input: ResultPanelInput): HTMLElement {
  const meta = input.metadata;
  const exclusions =
    meta.exclusions.length > 0
      ? meta.exclusions.map((item) => `${item.member_id} (${item.reason})`).join("; ")
      : "нет";
  const limitations = [
    "Оценка корреляционная по плану эксперимента; причинный вывод недоступен.",
    meta.n < 5
      ? `N=${String(meta.n)} мало: результат не является статистической уверенностью.`
      : `N=${String(meta.n)} независимых единиц.`,
    ...(meta.missing_count > 0
      ? [
          `Пропущено значений: ${String(meta.missing_count)} (причины указаны в таблице участников).`,
        ]
      : []),
    ...(input.limitationsExtra ?? []),
    PLANE_NOTE,
  ];
  const list = el("ul", { className: "lnt-exp-limitations" });
  for (const item of limitations) list.append(el("li", { text: item }));
  return el("div", { className: "lnt-exp-provenance" }, [
    el("h4", { className: "lnt-exp-provenance-title", text: "Маркировка результата" }),
    el("p", {
      className: "lnt-exp-meta-line",
      text: `Единицы: ${meta.units} · N=${String(meta.n)} · Рецепт: ${meta.estimator}, интервал: ${meta.interval_method}`,
    }),
    el("p", {
      className: "lnt-exp-meta-line",
      text: `Рецепт-источник: experiment ${String(meta.provenance.experiment_id ?? "—")} ревизия ${String(meta.provenance.experiment_revision ?? "—")}, estimand «${String(meta.provenance.estimand ?? "—")}»`,
    }),
    el("p", { className: "lnt-exp-meta-line", text: `Явные исключения: ${exclusions}` }),
    el("p", { className: "lnt-exp-meta-line", text: "Ограничения:" }),
    list,
  ]);
}
