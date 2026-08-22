/** Чистая модель научного отчёта (#/reports): ограничения и Markdown.
 * Данные приходят только из существующих контрактов бэкенда
 * (statistics-runs result envelope, детали сессий, /api/analysis/recipes);
 * ничего не выдумывается — недоступное помечается кодом причины. */

export interface ReportProvenance {
  experiment_id: string;
  experiment_revision: number;
  estimand: string;
  job_id: string;
  generated_at: string;
}

export interface ReportCore {
  units: string;
  sampling_unit: string;
  hierarchy: string[];
  n: number;
  missing_count: number;
  exclusions: { member_id: string; reason: string }[];
  estimator: string;
  interval_method: string;
}

export interface ReportEffectNumbers {
  mean_effect: number;
  median_effect: number;
  robust_effect: number;
  interval_low: number | null;
  interval_high: number | null;
  confidence_level?: number | null;
}

export type ReportOutcome =
  | { kind: "effect"; effect: ReportEffectNumbers; drift: ReportEffectNumbers | null }
  | { kind: "descriptive"; effect: ReportEffectNumbers }
  | { kind: "refusal"; reason_code: string };

/** Плоскость измерения по ch1_input_reference из metrics.json сессии. */
export interface ReportPlaneRow {
  session_id: string;
  available: boolean;
  reason_code: string | null;
  model_kind: string | null;
}

export interface ReportRecipeRow {
  recipe_id: string;
  name: string;
  sha256: string;
}

export interface ReportLimitation {
  code: string;
  detail: string;
}

export interface LimitationInput {
  outcome: ReportOutcome;
  core: ReportCore;
  planes: ReportPlaneRow[];
  unhealthySessions: { session_id: string; health: string }[];
  recipesLinked: boolean;
  /** Дополнительные ограничения из хранилища (например рваные группы). */
  extra?: ReportLimitation[];
}

const CAUSAL_ESTIMATORS = new Set(["qualified_within_run_contrast"]);

/** Машиночитаемые ограничения с русскими пояснениями (аналог Limitation). */
export function deriveLimitations(input: LimitationInput): ReportLimitation[] {
  const limitations: ReportLimitation[] = [...(input.extra ?? [])];
  if (input.outcome.kind === "refusal") {
    limitations.push({
      code: "statistics_refusal",
      detail: `Расчёт контраста заблокирован бэкендом, причина: ${input.outcome.reason_code}. Числовые эффекты не выдаются.`,
    });
  }
  if (input.outcome.kind === "descriptive") {
    limitations.push({
      code: "descriptive_no_interval",
      detail:
        "Описательная оценка без доверительного интервала: N ниже минимума инференции; это не является статистической уверенностью.",
    });
  }
  if (input.outcome.kind !== "refusal" && CAUSAL_ESTIMATORS.has(input.core.estimator)) {
    limitations.push({
      code: "causal_inference_not_available",
      detail:
        "Квалифицированный внутрисерийный контраст: причинный вывод недоступен, оценка описывает наблюдаемую разницу условий.",
    });
  }
  if (input.core.missing_count > 0) {
    limitations.push({
      code: "missing_values",
      detail: `Пропущенные значения: ${String(input.core.missing_count)}. Они исключены из расчёта и учтены в метаданных.`,
    });
  }
  for (const exclusion of input.core.exclusions) {
    limitations.push({
      code: "qc_exclusions",
      detail: `Исключение QC: участник ${exclusion.member_id}, причина ${exclusion.reason}.`,
    });
  }
  const unavailablePlanes = input.planes.filter((plane) => !plane.available);
  if (unavailablePlanes.length > 0) {
    limitations.push({
      code: "input_reference_unavailable",
      detail: `Приведение ко входу недоступно для ${String(unavailablePlanes.length)} плоскости(ей): ${unavailablePlanes
        .map((plane) => `${plane.session_id} (${plane.reason_code ?? "reason_unknown"})`)
        .join("; ")}.`,
    });
  }
  if (input.unhealthySessions.length > 0) {
    limitations.push({
      code: "unhealthy_sessions_excluded",
      detail: `Сессии с плохим здоровьем исключены из расчёта: ${input.unhealthySessions
        .map((item) => `${item.session_id} (${item.health})`)
        .join("; ")}.`,
    });
  }
  if (!input.recipesLinked) {
    limitations.push({
      code: "recipes_unlinked",
      detail:
        "Бэкенд не связывает эксперименты с рецептами анализа через HTTP API; список рецептов приведён справочно.",
    });
  }
  return limitations;
}

export interface ReportDraft {
  title: string;
  provenance: ReportProvenance;
  core: ReportCore;
  outcome: ReportOutcome;
  planes: ReportPlaneRow[];
  recipes: ReportRecipeRow[];
  limitations: ReportLimitation[];
}

function escapeCell(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/\n/g, " ");
}

/** Единый формат чисел превью и выгрузки: 4 знака, как в панели сравнения.
 * Плавающая точка бэкенда (1.5999999999999996) не должна попадать в отчёт. */
export function formatMetric(value: number): string {
  return Number(value).toFixed(4);
}

function effectLines(name: string, effect: ReportEffectNumbers): string[] {
  const lines = [
    `- ${escapeCell(name)}: среднее ${formatMetric(effect.mean_effect)}, медиана ${formatMetric(effect.median_effect)}, робастное ${formatMetric(effect.robust_effect)}`,
  ];
  if (effect.interval_low !== null && effect.interval_high !== null) {
    const level =
      typeof effect.confidence_level === "number" ? formatMetric(effect.confidence_level) : "0.95";
    lines.push(
      `  - интервал [${formatMetric(effect.interval_low)}; ${formatMetric(effect.interval_high)}] (уровень ${level})`,
    );
  }
  return lines;
}

function outcomeSection(draft: ReportDraft): string[] {
  const lines: string[] = ["## Результат", ""];
  const outcome = draft.outcome;
  if (outcome.kind === "refusal") {
    lines.push(`Статус: отказ расчёта. Причина: \`${outcome.reason_code}\`.`, "");
    return lines;
  }
  lines.push(...effectLines("Эффект", outcome.effect));
  if (outcome.kind === "effect" && outcome.drift !== null) {
    lines.push(...effectLines("Дрейф A (A2−A1)", outcome.drift));
  }
  lines.push("");
  return lines;
}

/** Детерминированный Markdown-отчёт: те же данные, что показаны в превью. */
export function composeReportMarkdown(draft: ReportDraft): string {
  const lines: string[] = [
    `# Отчёт: ${escapeCell(draft.title)}`,
    "",
    "## Происхождение (provenance)",
    "",
    `- experiment_id: \`${draft.provenance.experiment_id}\` (revision ${String(draft.provenance.experiment_revision)})`,
    `- estimand: \`${draft.provenance.estimand}\``,
    `- job_id: \`${draft.provenance.job_id}\``,
    `- отчёт собран: ${draft.provenance.generated_at}`,
    "",
    "## Единицы и объём выборки",
    "",
    `- единицы: ${escapeCell(draft.core.units)}`,
    `- N = ${String(draft.core.n)} (sampling_unit: ${escapeCell(draft.core.sampling_unit)})`,
    `- иерархия: ${draft.core.hierarchy.map(escapeCell).join(" → ") || "—"}`,
    `- пропущено значений: ${String(draft.core.missing_count)}`,
    "",
    "## Оценка",
    "",
    `- estimator: \`${draft.core.estimator}\``,
    `- interval_method: \`${draft.core.interval_method}\``,
    "",
  ];
  lines.push(...outcomeSection(draft));
  lines.push("## Плоскости измерения", "");
  if (draft.planes.length === 0) {
    lines.push("Данные о плоскостях измерения недоступны (анализ сессий отсутствует).", "");
  }
  for (const plane of draft.planes) {
    const state = plane.available
      ? `приведён ко входу (${plane.model_kind ?? "model"})`
      : `недоступно (${plane.reason_code ?? "reason_unknown"})`;
    lines.push(`- ${escapeCell(plane.session_id)}: ${state}`);
  }
  lines.push("", "## Рецепты анализа", "");
  if (draft.recipes.length === 0) {
    lines.push("Рецепты анализа не зарегистрированы.", "");
  }
  for (const recipe of draft.recipes) {
    lines.push(
      `- ${escapeCell(recipe.name)} (\`${recipe.recipe_id}\`, sha256 \`${recipe.sha256}\`)`,
    );
  }
  lines.push("", "## Ограничения", "");
  for (const limitation of draft.limitations) {
    lines.push(`- \`${limitation.code}\`: ${escapeCell(limitation.detail)}`);
  }
  if (draft.limitations.length === 0) lines.push("- не обнаружены");
  lines.push("");
  return lines.join("\n");
}
