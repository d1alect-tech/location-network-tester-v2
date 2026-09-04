/** Синхронизация строк участников со сравнением/трендами (T11: выделено из
 * experimentsWorkspace). Чистые перекладки MemberRow → строки анализа и
 * чтение метрики из detail; клиент и вьюхи приходят аргументами. */

import type { LntApiClient } from "../../api/client";
import type { SessionDetailPayload } from "../../api/types-plots";
import type { ComparisonView } from "./comparisonView";
import type { ExperimentDetail } from "./experimentsStore";
import { currentState } from "./memberQc";
import type { MemberRow } from "./memberTableView";
import type { TrendView } from "./trendView";

export function metricValue(detail: SessionDetailPayload, featureKey: string): number | null {
  const analysis = detail.analysis;
  if (typeof analysis !== "object" || analysis === null) return null;
  const metrics = (analysis as Record<string, unknown>).metrics;
  if (typeof metrics === "object" && metrics !== null) {
    const direct = (metrics as Record<string, unknown>)[featureKey];
    if (typeof direct === "number") return direct;
  }
  const flat = (analysis as Record<string, unknown>)[featureKey];
  return typeof flat === "number" ? flat : null;
}

export async function loadHealthMap(
  client: LntApiClient,
  sessions: string[],
): Promise<Map<string, string>> {
  try {
    const page = await client.catalogSessions({ page_size: 200 });
    const map = new Map<string, string>();
    for (const session of page.items) map.set(session.id, String(session.health ?? "ok"));
    return map;
  } catch {
    return new Map(sessions.map((id) => [id, "health_unavailable"]));
  }
}

export function toTrendRows(rows: MemberRow[]): {
  sessionId: string;
  condition: string;
  order: number;
  value: null;
  timestamp: null;
}[] {
  return rows
    .filter((row) => currentState(row.inclusion) !== "excluded")
    .map((row) => ({
      sessionId: row.sessionId,
      condition: row.conditionId,
      order: row.order,
      value: null,
      timestamp: null,
    }));
}

/** Раздать текущие строки участников в сравнение и тренды. */
export function syncComparisonAndTrends(
  comparison: ComparisonView,
  trends: TrendView,
  detail: ExperimentDetail | null,
  rows: MemberRow[],
): void {
  if (!detail) return;
  comparison.setContext(detail, rows);
  trends.setRows(
    toTrendRows(rows),
    String(detail.experiment.primary_estimands?.[0]?.feature_key ?? ""),
  );
}

/** Группы включённых sessionId по условиям для спектрального оверлея. */
export function overlayGroups(rows: MemberRow[]): { label: string; sessionIds: string[] }[] {
  const groups = new Map<string, string[]>();
  for (const row of rows) {
    if (currentState(row.inclusion) === "excluded") continue;
    const list = groups.get(row.conditionId) ?? [];
    list.push(row.sessionId);
    groups.set(row.conditionId, list);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, ids]) => ({ label, sessionIds: ids }));
}
