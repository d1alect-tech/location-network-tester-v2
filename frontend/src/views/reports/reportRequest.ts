/** Чистые помощники сборки запроса статистики и разбора ответа для отчётов.
 * Никакого I/O: функции принимают уже собранные данные (значения участников,
 * детали сессий) — это позволяет покрывать их юнит-тестами без сети. */

import type {
  AbaUnitInput,
  OpenRecord,
  PairInput,
  StatisticsResultEnvelope,
  StatisticsRunRequest,
} from "../../api/types-research";
import type {
  ReportEffectNumbers,
  ReportLimitation,
  ReportOutcome,
  ReportPlaneRow,
} from "./reportModel";

export interface SessionAnalysisLike {
  analysis: Record<string, unknown> | null;
}

export function metricValue(detail: SessionAnalysisLike, featureKey: string): number | null {
  const analysis = detail.analysis;
  if (analysis === null) return null;
  const metrics = analysis.metrics;
  if (typeof metrics === "object" && metrics !== null) {
    const direct = (metrics as Record<string, unknown>)[featureKey];
    if (typeof direct === "number") return direct;
  }
  const flat = (analysis as Record<string, unknown>)[featureKey];
  return typeof flat === "number" ? flat : null;
}

/** Плоскость измерения по ch1_input_reference из metrics.json сессии. */
export function planeRowOf(sessionId: string, detail: SessionAnalysisLike): ReportPlaneRow {
  const reference = detail.analysis?.ch1_input_reference;
  if (typeof reference !== "object" || reference === null) {
    return {
      session_id: sessionId,
      available: false,
      reason_code: "analysis_unavailable",
      model_kind: null,
    };
  }
  const record = reference as Record<string, unknown>;
  const available = record.status === "available";
  return {
    session_id: sessionId,
    available,
    reason_code: available ? null : String(record.reason_code ?? "reason_unknown"),
    model_kind: typeof record.model_kind === "string" ? record.model_kind : null,
  };
}

function effectNumbers(raw: unknown): ReportEffectNumbers | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  if (
    typeof record.mean_effect !== "number" ||
    typeof record.median_effect !== "number" ||
    typeof record.robust_effect !== "number"
  ) {
    return null;
  }
  const interval =
    typeof record.interval === "object" && record.interval !== null
      ? (record.interval as Record<string, unknown>)
      : null;
  return {
    mean_effect: record.mean_effect,
    median_effect: record.median_effect,
    robust_effect: record.robust_effect,
    interval_low: typeof interval?.low === "number" ? interval.low : null,
    interval_high: typeof interval?.high === "number" ? interval.high : null,
    confidence_level:
      typeof interval?.confidence_level === "number" ? interval.confidence_level : null,
  };
}

export function outcomeOfEnvelope(envelope: StatisticsResultEnvelope): ReportOutcome {
  if (envelope.result_kind === "refusal") {
    return {
      kind: "refusal",
      reason_code: String((envelope.result as Record<string, unknown>).reason_code ?? "unknown"),
    };
  }
  if (envelope.result_kind === "effect") {
    const result = envelope.result as Record<string, unknown>;
    const effect = effectNumbers(result.effect);
    if (effect === null) throw new Error("результат расчёта не содержит корректного эффекта");
    const drift = effectNumbers(result.drift);
    return { kind: "effect", effect, drift };
  }
  const effect = effectNumbers(envelope.result);
  if (effect === null) throw new Error("описательный результат не содержит корректных чисел");
  return { kind: "descriptive", effect };
}

export interface ProtocolShape {
  /** Уникальные условия в порядке шагов протокола. */
  orderedConditions: string[];
}

/** Группы включённых участников в порядке шагов протокола; внутри условия
 * участники упорядочены по order (выравнивание юнитов A/B/A). */
export function groupedInProtocolOrder(shape: ProtocolShape, members: OpenRecord[]): string[][] {
  const byCondition = new Map<string, { sessionId: string; order: number }[]>();
  for (const member of members) {
    const conditionId = String(member.condition_id);
    const list = byCondition.get(conditionId) ?? [];
    list.push({ sessionId: String(member.session_id), order: Number(member.order) });
    byCondition.set(conditionId, list);
  }
  const orderedConditions =
    shape.orderedConditions.length > 0 ? shape.orderedConditions : [...byCondition.keys()];
  return orderedConditions
    .map((conditionId) =>
      (byCondition.get(conditionId) ?? [])
        .sort((a, b) => a.order - b.order)
        .map((item) => item.sessionId),
    )
    .filter((ids) => ids.length > 0);
}

/** Разные по размеру группы условий: пары формируются позиционно —
 * это честное ограничение отчёта, а не тихая перестановка юнитов. */
export function raggedGroupsLimitation(groups: string[][]): ReportLimitation[] {
  const sizes = new Set(groups.map((group) => group.length));
  if (groups.length < 2 || sizes.size <= 1) return [];
  return [
    {
      code: "ragged_condition_groups",
      detail: `Условия содержат разное число участников (${groups
        .map((group) => String(group.length))
        .join(
          "/",
        )}); пары формируются позиционно по порядку протокола, выравнивание юнитов не гарантируется.`,
    },
  ];
}

/** Замечания здоровья у включённых участников — информационное ограничение:
 * расчёт идёт как есть, решение о включении принимает оператор. */
export function healthNotesLimitation(
  notes: { session_id: string; health: string }[],
): ReportLimitation[] {
  if (notes.length === 0) return [];
  return [
    {
      code: "sessions_with_health_notes",
      detail: `Сессии с замечаниями здоровья каталога включены в расчёт как есть (решение о включении — за оператором в разделе «Эксперименты»): ${notes
        .map((item) => `${item.session_id} (${item.health})`)
        .join("; ")}.`,
    },
  ];
}

export function buildStatisticsRequest(
  protocolKind: string,
  groups: string[][],
  values: Map<string, number>,
  featureKey: string,
  units: string,
): StatisticsRunRequest {
  const metricOf = (sessionId: string): number | null => values.get(sessionId) ?? null;
  if (protocolKind === "aba") {
    const [g1 = [], g2 = [], g3 = []] = groups;
    const abaUnits: AbaUnitInput[] = [];
    const count = Math.min(g1.length, g2.length, g3.length);
    for (let index = 0; index < count; index += 1) {
      const a1 = metricOf(g1[index] ?? "");
      const b = metricOf(g2[index] ?? "");
      const a2 = metricOf(g3[index] ?? "");
      if (a1 === null || b === null || a2 === null) continue;
      abaUnits.push({ unit_id: g1[index] ?? "", value_a1: a1, value_b: b, value_a2: a2 });
    }
    return { kind: "aba", estimand: featureKey, units, aba_units: abaUnits };
  }
  const left = groups[0] ?? [];
  const right = groups[1] ?? [];
  const pairs: PairInput[] = [];
  const paired = Math.min(left.length, right.length);
  for (let index = 0; index < paired; index += 1) {
    const valueA = metricOf(left[index] ?? "");
    const valueB = metricOf(right[index] ?? "");
    if (valueA === null || valueB === null) continue;
    pairs.push({
      unit_id: `${left[index] ?? ""}~${right[index] ?? ""}`,
      value_a: valueA,
      value_b: valueB,
    });
  }
  return {
    kind: protocolKind as "ab" | "repeated_blocks" | "cohort" | "longitudinal",
    estimand: featureKey,
    units,
    pairs,
  };
}
