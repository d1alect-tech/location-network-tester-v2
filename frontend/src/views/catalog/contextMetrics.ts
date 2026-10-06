/** Метрики сессии для сводки инспектора: длительность, частота сети, THD.
 * Источник — GET /api/sessions/{id} (манифест + анализ v1-пейлоада).
 * Ничего не додумывается: отсутствующее значение остаётся null с причиной,
 * пропущенное не подменяется нулём (контракт «unavailable, never fabricated»). */

import { sessionMetricValue } from "../../api/sessionMetrics";
import type { SessionDetailPayload } from "../../api/types-plots";

export interface SessionMetrics {
  durationS: number | null;
  durationReason: string | null;
  mainsHz: number | null;
  mainsReason: string | null;
  thdRatio: number | null;
  thdReason: string | null;
  cycles: number | null;
}

export const EMPTY_METRICS: SessionMetrics = {
  durationS: null,
  durationReason: "в манифесте сессии нет длительности",
  mainsHz: null,
  mainsReason: "частота сети не собрана в анализе сессии",
  thdRatio: null,
  thdReason: "THD не собран в анализе сессии",
  cycles: null,
};

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function readSessionMetrics(detail: SessionDetailPayload | null): SessionMetrics {
  if (detail === null) return EMPTY_METRICS;
  const durationS = finite(detail.manifest.duration_s);
  const mainsHz =
    sessionMetricValue(detail, "line_quality.fundamental_hz") ??
    finite(detail.manifest.line_frequency_hz);
  const thdRatio = sessionMetricValue(detail, "line_quality.thd_ratio");
  const cycles = sessionMetricValue(detail, "line_quality.cycles_analyzed");
  return {
    durationS,
    durationReason: durationS === null ? EMPTY_METRICS.durationReason : null,
    mainsHz,
    mainsReason: mainsHz === null ? EMPTY_METRICS.mainsReason : null,
    thdRatio,
    thdReason: thdRatio === null ? EMPTY_METRICS.thdReason : null,
    cycles,
  };
}
