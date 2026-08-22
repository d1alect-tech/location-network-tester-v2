/** Хранилище отчётов (#/reports): сборка provenance-отчёта из СУЩЕСТВУЮЩИХ
 * контрактов бэкенда — statistics-runs (расчёт), детали сессий (плоскости
 * ch1_input_reference), /api/analysis/recipes (справочно), каталог (health).
 * HTTP-маршрутов для готовых отчётов у бэкенда нет — превью и выгрузка
 * собираются клиентом из этих данных, без выдуманных эндпоинтов. */

import type { LntApiClient } from "../../api/client";
import type { OpenRecord, StatisticsResultEnvelope } from "../../api/types-research";
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
  groupedInProtocolOrder,
  healthNotesLimitation,
  metricValue,
  outcomeOfEnvelope,
  planeRowOf,
  raggedGroupsLimitation,
} from "./reportRequest";

const POLL_INTERVAL_MS = 300;
const POLL_LIMIT = 40;
const DEFAULT_UNITS = "В²/Гц";

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
    const featureKey = String(experiment.primary_estimands?.[0]?.feature_key ?? "band_mid_total");
    const units = input.units?.trim() || DEFAULT_UNITS;

    const healthBySession = await this.loadHealth(signal);
    // Семантика рабочей области «Эксперименты»: включение участника — явное
    // действие оператора, health каталога — вердикт QC на экране. Отчёт
    // включает всех участников, чьи значения удалось собрать; недоступные
    // значения и замечания здоровья фиксируются типизированными ограничениями.
    const values = await this.collectValues(detail.members, featureKey, signal);
    const excluded: { session_id: string; health: string }[] = [];
    const included = detail.members.filter((member) => {
      const sessionId = String(member.session_id);
      if (values.has(sessionId)) return true;
      excluded.push({ session_id: sessionId, health: "value_unavailable" });
      return false;
    });
    const healthNotes: { session_id: string; health: string }[] = [];
    for (const member of included) {
      const sessionId = String(member.session_id);
      const health = healthBySession.get(sessionId) ?? "health_unavailable";
      if (health !== "ok") healthNotes.push({ session_id: sessionId, health });
    }

    const orderedConditions = [...detail.experiment.steps]
      .sort((a, b) => Number(a.order) - Number(b.order))
      .map((step) => String(step.condition_id));
    const groups = groupedInProtocolOrder({ orderedConditions }, included);
    const extraLimitations = [
      ...raggedGroupsLimitation(groups),
      ...healthNotesLimitation(healthNotes),
    ];
    const request = buildStatisticsRequest(
      String(detail.experiment.protocol.kind),
      groups,
      values,
      featureKey,
      units,
    );
    const snapshot = await this.client.statistics.submit(String(experiment.experiment_id), request);
    const envelope = await this.pollResult(snapshot.job_id, signal);

    const planes: ReportPlaneRow[] = [];
    for (const member of included) {
      const sessionId = String(member.session_id);
      planes.push(planeRowOf(sessionId, await this.client.plots.detail(sessionId, { signal })));
    }
    const recipes = await this.client.analysis.recipes({ signal }).catch(() => []);

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
        sha256: recipe.sha256,
      })),
      limitations,
    };
    return { draft, markdown: composeReportMarkdown(draft) };
  }

  private async loadHealth(signal: AbortSignal): Promise<Map<string, string>> {
    try {
      const page = await this.client.catalogSessions({ page_size: 200 }, { signal });
      const map = new Map<string, string>();
      for (const session of page.items) map.set(session.id, String(session.health ?? "ok"));
      return map;
    } catch {
      return new Map();
    }
  }

  /** Значения estimand по всем участникам; сессии с недоступными данными
   * пропускаются (ошибка сети/разбора) и попадают в ограничения. */
  private async collectValues(
    members: OpenRecord[],
    featureKey: string,
    signal: AbortSignal,
  ): Promise<Map<string, number>> {
    const map = new Map<string, number>();
    for (const member of members) {
      const sessionId = String(member.session_id);
      try {
        const value = metricValue(
          await this.client.plots.detail(sessionId, { signal }),
          featureKey,
        );
        if (value !== null) map.set(sessionId, value);
      } catch (error) {
        if (signal.aborted) throw error;
      }
    }
    return map;
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
