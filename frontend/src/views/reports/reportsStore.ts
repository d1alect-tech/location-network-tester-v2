/** Хранилище отчётов (#/reports): сборка provenance-отчёта из СУЩЕСТВУЮЩИХ
 * контрактов бэкенда — statistics-runs (расчёт), детали сессий (плоскости
 * ch1_input_reference), /api/analysis/recipes (справочно), каталог (health).
 * HTTP-маршрутов для готовых отчётов у бэкенда нет — превью и выгрузка
 * собираются клиентом из этих данных, без выдуманных эндпоинтов. */

import type { LntApiClient } from "../../api/client";
import { knownMetricUnits } from "../../api/sessionMetrics";
import type { StatisticsResultEnvelope } from "../../api/types-research";
import type { ExperimentDetail } from "../experiments/experimentsStore";
import { ExperimentsStore } from "../experiments/experimentsStore";
import {
  type ReportCore,
  type ReportDraft,
  type ReportPlaneRow,
  composeReportMarkdown,
  deriveLimitations,
} from "./reportModel";
import {
  buildStatisticsRequest,
  completeObservationSessionIds,
  groupedInProtocolOrder,
  healthNotesLimitation,
  outcomeOfEnvelope,
  planeRowOf,
  raggedGroupsLimitation,
} from "./reportRequest";
import { collectReportValues, loadReportHealth } from "./reportSources";

const POLL_INTERVAL_MS = 300;
const POLL_LIMIT = 40;

export interface ReportsStoreOptions {
  client: LntApiClient;
}

export interface BuildReportInput {
  units?: string;
}

export interface BuildReportResult {
  draft: ReportDraft;
  markdown: string;
}

export class ReportsStore {
  readonly experiments;
  readonly detail;
  private readonly client: LntApiClient;
  private controller = new AbortController();

  constructor(options: ReportsStoreOptions) {
    this.client = options.client;
    const experimentsStore = new ExperimentsStore({ client: options.client });
    this.experiments = experimentsStore.list;
    this.detail = experimentsStore.detail;
  }

  abort(): void {
    this.controller.abort();
  }

  /** Полный цикл сборки отчёта для загруженного эксперимента. */
  async buildReport(
    detail: ExperimentDetail,
    input: BuildReportInput = {},
  ): Promise<BuildReportResult> {
    this.controller.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const experiment = detail.experiment;
    const featureKey = String(experiment.primary_estimands?.[0]?.feature_key ?? "").trim();
    if (featureKey === "") throw new Error("В эксперименте не указан оцениваемый признак");
    const units = input.units?.trim() || knownMetricUnits(featureKey);
    if (!units) throw new Error(`Для признака «${featureKey}» укажите единицы измерения`);

    const health = await loadReportHealth(this.client, signal);
    signal.throwIfAborted();
    const healthBySession = health.map;
    // Семантика рабочей области «Эксперименты»: включение участника — явное
    // действие оператора, health каталога — вердикт QC на экране. Отчёт
    // включает всех участников, чьи значения удалось собрать; недоступные
    // значения и замечания здоровья фиксируются типизированными ограничениями.
    const collected = await collectReportValues(this.client, detail.members, featureKey, signal);
    signal.throwIfAborted();
    const values = collected.values;
    const excluded: { session_id: string; health: string }[] = [];
    for (const member of detail.members) {
      const sessionId = String(member.session_id);
      if (!values.has(sessionId))
        excluded.push({ session_id: sessionId, health: "value_unavailable" });
    }

    const orderedConditions = [...detail.experiment.steps]
      .sort((a, b) => Number(a.order) - Number(b.order))
      .map((step) => String(step.condition_id));
    const groups = groupedInProtocolOrder({ orderedConditions }, detail.members);
    const completeSessionIds = completeObservationSessionIds(
      String(detail.experiment.protocol.kind),
      groups,
      values,
    );
    const contributors = detail.members.filter((member) =>
      completeSessionIds.has(String(member.session_id)),
    );
    const healthNotes: { session_id: string; health: string }[] = [];
    for (const member of contributors) {
      const sessionId = String(member.session_id);
      const health = healthBySession.get(sessionId) ?? "health_unavailable";
      if (health !== "ok") healthNotes.push({ session_id: sessionId, health });
    }
    const incomplete = detail.members.filter(
      (member) => !completeSessionIds.has(String(member.session_id)),
    );
    const extraLimitations = [
      ...raggedGroupsLimitation(groups),
      ...healthNotesLimitation(healthNotes),
      ...(health.warningMessage === null
        ? []
        : [
            {
              code: "catalog_health_unavailable",
              detail: `Состояние каталога недоступно: ${health.warningMessage}. Метки здоровья не учтены; повторите сборку для уточнения.`,
            },
          ]),
      ...(collected.failures.length === 0
        ? []
        : [
            {
              code: "values_unavailable",
              detail: `Значения недоступны и исключены из расчёта: ${collected.failures
                .map((item) => `${item.session_id} (${item.message})`)
                .join("; ")}. Повторите сборку после восстановления данных.`,
            },
          ]),
      ...(incomplete.length === 0
        ? []
        : [
            {
              code: "incomplete_observations",
              detail: `Сессии не вошли в полные наблюдения: ${incomplete
                .map((member) => {
                  const sessionId = String(member.session_id);
                  return `${sessionId} (${values.has(sessionId) ? "нет полной пары по протоколу" : "значение недоступно"})`;
                })
                .join("; ")}. Они не учитываются в N, плоскостях измерения и статистике.`,
            },
          ]),
    ];
    const request = buildStatisticsRequest(
      String(detail.experiment.protocol.kind),
      groups,
      values,
      featureKey,
      units,
    );
    const observationCount =
      request.kind === "aba" ? request.aba_units?.length : request.pairs?.length;
    if ((observationCount ?? 0) === 0) {
      throw new Error(
        `Для признака «${featureKey}» нет полных наблюдений по протоколу. Выберите доступный признак или восстановите анализ сессий`,
      );
    }
    signal.throwIfAborted();
    const snapshot = await this.client.statistics.submit(
      String(experiment.experiment_id),
      request,
      {
        signal,
      },
    );
    signal.throwIfAborted();
    const envelope = await this.pollResult(snapshot.job_id, signal);
    signal.throwIfAborted();

    const planes: ReportPlaneRow[] = [];
    for (const member of contributors) {
      const sessionId = String(member.session_id);
      planes.push(planeRowOf(sessionId, await this.client.plots.detail(sessionId, { signal })));
      signal.throwIfAborted();
    }
    let recipes: { recipe_id: string; name: string }[] = [];
    let recipesError: string | null = null;
    try {
      recipes = await this.client.analysis.recipes({ signal });
      signal.throwIfAborted();
    } catch (error) {
      if (signal.aborted) throw error;
      recipesError = error instanceof Error ? error.message : String(error);
    }
    if (recipesError !== null) {
      extraLimitations.push({
        code: "recipes_load_failed",
        detail: `Не удалось загрузить рецепты: ${recipesError}. Список показан пустым; повторите сборку.`,
      });
    }

    const core: ReportCore = {
      units: envelope.metadata.units,
      sampling_unit: envelope.metadata.sampling_unit,
      hierarchy: [...envelope.metadata.hierarchy],
      n: envelope.metadata.n,
      missing_count: envelope.metadata.missing_count,
      exclusions: envelope.metadata.exclusions.map((item) => ({
        member_id: item.member_id,
        reason: item.reason,
      })),
      estimator: envelope.metadata.estimator,
      interval_method: envelope.metadata.interval_method,
    };
    const outcome = outcomeOfEnvelope(envelope);
    const limitations = deriveLimitations({
      outcome,
      core,
      planes,
      unhealthySessions: excluded,
      recipesLinked: false,
      extra: extraLimitations,
    });
    const title = String(experiment.title ?? experiment.experiment_id);
    const draft: ReportDraft = {
      title,
      provenance: {
        experiment_id: String(experiment.experiment_id),
        experiment_revision: Number(experiment.revision ?? 0),
        estimand: envelope.metadata.provenance.estimand as string,
        job_id: String(envelope.metadata.provenance.job_id ?? snapshot.job_id),
        generated_at: new Date().toISOString(),
      },
      core,
      outcome,
      planes,
      recipes: recipes.map((recipe) => ({
        recipe_id: recipe.recipe_id,
        name: recipe.name,
      })),
      limitations,
    };
    return { draft, markdown: composeReportMarkdown(draft) };
  }

  private async pollResult(jobId: string, signal: AbortSignal): Promise<StatisticsResultEnvelope> {
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      const payload = await this.client.statistics.result(jobId, { signal });
      if ("result_kind" in payload) return payload as StatisticsResultEnvelope;
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
    throw new Error("превышено время ожидания результата статистики");
  }
}
