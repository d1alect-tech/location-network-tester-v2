/** Задачи сравнения (C3c): проверка сравнимости → запуск statistics-run →
 * опрос результата. Вынесено из comparisonView дословно: тайминги опроса,
 * гейт сравнимости и тексты баннеров байт-идентичны. Лист не импортирует
 * experimentsWorkspace — цикл разорван через setContext/abort ядра. */

import type { LntApiClient } from "../../api/client";
import type {
  ComparabilityReport,
  StatisticsResultEnvelope,
  StatisticsRunRequest,
} from "../../api/types-research";
import { announcePolite } from "../../components/primitives/status";
import type { ExperimentDetail } from "./experimentsStore";
import type { MemberRow } from "./memberTableView";

export const POLL_INTERVAL_MS = 300;
export const POLL_LIMIT = 40;

export type ComparisonBannerTone = "ok" | "warn" | "error";

export type ComparisonProtocolKind = "ab" | "aba" | "repeated_blocks" | "cohort" | "longitudinal";

export interface ComparabilityJobInput {
  client: Pick<LntApiClient, "research" | "statistics">;
  detail: ExperimentDetail | null;
  signal: AbortSignal;
  groupedInProtocolOrder(): MemberRow[][];
  onReport(report: ComparabilityReport): void;
  showBanner(message: string, tone: ComparisonBannerTone): void;
  renderReport(report: ComparabilityReport): void;
}

export interface AnalysisJobInput {
  client: Pick<LntApiClient, "research" | "statistics">;
  detail: ExperimentDetail | null;
  lastReport: ComparabilityReport | null;
  featureKey: string;
  units: string;
  seed: number;
  signal: AbortSignal;
  buildStatisticsRequest(
    kind: ComparisonProtocolKind,
    featureKey: string,
    units: string,
    seed: number,
    signal: AbortSignal,
  ): Promise<StatisticsRunRequest>;
  showBanner(message: string, tone: ComparisonBannerTone): void;
  renderEnvelope(envelope: StatisticsResultEnvelope): void;
}

export async function runComparability(input: ComparabilityJobInput): Promise<void> {
  const { client, detail, signal } = input;
  if (!detail) {
    input.showBanner(
      "Нет данных эксперимента для проверки сравнимости. Сначала выберите эксперимент.",
      "warn",
    );
    return;
  }
  const groups = input.groupedInProtocolOrder();
  if (groups.length < 2) {
    input.showBanner(
      "Для проверки сравнимости нужно минимум два условия с включёнными участниками.",
      "warn",
    );
    return;
  }
  const first = groups[0]?.[0];
  const second = groups[1]?.[0];
  if (!first || !second) {
    input.showBanner("В одном из условий нет доступных участников.", "warn");
    return;
  }
  try {
    const report = await client.research.comparabilityCheck(
      {
        left: { session_id: first.sessionId },
        right: { session_id: second.sessionId },
      },
      { signal },
    );
    input.onReport(report);
    input.renderReport(report);
  } catch (error) {
    if (!signal.aborted)
      input.showBanner(`Проверка сравнимости не удалась: ${String(error)}`, "error");
  }
}

export async function runAnalysis(input: AnalysisJobInput): Promise<void> {
  const { client, detail, lastReport, featureKey, units, seed, signal } = input;
  if (!detail) {
    input.showBanner("Нет данных эксперимента для расчёта. Сначала выберите эксперимент.", "warn");
    return;
  }
  if (lastReport !== null && !lastReport.comparable) {
    input.showBanner("Расчёт заблокирован: сравнимость не подтверждена.", "warn");
    return;
  }
  const kind = String(detail.experiment.protocol.kind);
  try {
    const request = await input.buildStatisticsRequest(
      kind as ComparisonProtocolKind,
      featureKey,
      units,
      seed,
      signal,
    );
    const snapshot = await client.statistics.submit(detail.experiment.experiment_id, request);
    const envelope = await pollResult(client, snapshot.job_id, signal);
    input.renderEnvelope(envelope);
    announcePolite("Результат сравнения получен");
  } catch (error) {
    if (!signal.aborted)
      input.showBanner(
        `Расчёт не выполнен: ${error instanceof Error ? error.message : String(error)}`,
        "error",
      );
  }
}

export async function pollResult(
  client: Pick<LntApiClient, "research" | "statistics">,
  jobId: string,
  signal: AbortSignal,
): Promise<StatisticsResultEnvelope> {
  for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
    const payload = await client.statistics.result(jobId, { signal });
    if ("result_kind" in payload) return payload as StatisticsResultEnvelope;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  throw new Error("превышено время ожидания результата статистики");
}
