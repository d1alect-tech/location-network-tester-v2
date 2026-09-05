/** Чистые построители запросов сравнения (todo 43, волна C3).
 * Выделены из comparisonView.ts без изменения поведения: гейт
 * lastReport.comparable и дельты B−A живут в виде, баннер missing→warn
 * побайтово тот же. Зависимости (detail/rows/valueSource/notify) — явные
 * параметры; DOM и клиент сюда не импортируются. */

import type { AbaUnitInput, PairInput } from "../../api/types-research";
import type { ExperimentDetail } from "./experimentsStore";
import { currentState } from "./memberQc";
import type { MemberRow } from "./memberTableView";
import type { EffectView } from "./resultPanel";

export function effectFromPayload(raw: unknown): EffectView | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  const mean = record.mean_effect;
  const median = record.median_effect;
  const robust = record.robust_effect;
  if (typeof mean !== "number" || typeof median !== "number" || typeof robust !== "number")
    return null;
  const interval = record.interval;
  const low =
    typeof interval === "object" &&
    interval !== null &&
    typeof (interval as Record<string, unknown>).low === "number"
      ? ((interval as Record<string, number>).low ?? null)
      : null;
  const high =
    typeof interval === "object" &&
    interval !== null &&
    typeof (interval as Record<string, unknown>).high === "number"
      ? ((interval as Record<string, number>).high ?? null)
      : null;
  return { mean, median, robust, intervalLow: low, intervalHigh: high };
}

export type ValueSource = (
  sessionId: string,
  featureKey: string,
  signal: AbortSignal,
) => Promise<number | null>;

export type NotifyTone = "ok" | "warn" | "error";

export type Notify = (message: string, tone: NotifyTone) => void;

export function includedByCondition(rows: MemberRow[]): Map<string, MemberRow[]> {
  const map = new Map<string, MemberRow[]>();
  for (const row of rows) {
    if (currentState(row.inclusion) === "excluded") continue;
    const list = map.get(row.conditionId) ?? [];
    list.push(row);
    map.set(row.conditionId, list);
  }
  for (const list of map.values()) list.sort((a, b) => a.order - b.order);
  return map;
}

/** Условия в порядке шагов протокола (не по алфавиту): для A/B/A критично. */
export function orderedConditions(detail: ExperimentDetail | null): string[] {
  const steps = detail?.experiment.steps ?? [];
  return [...steps]
    .sort((a, b) => Number(a.order) - Number(b.order))
    .map((step) => String(step.condition_id));
}

/** Группы включённых участников в порядке протокола. */
export function groupedInProtocolOrder(
  detail: ExperimentDetail | null,
  rows: MemberRow[],
): MemberRow[][] {
  const included = includedByCondition(rows);
  return orderedConditions(detail)
    .map((conditionId) => included.get(conditionId) ?? [])
    .filter((group) => group.length > 0);
}

export type PairsKind = "ab" | "repeated_blocks" | "cohort" | "longitudinal";

export interface PairsRequest {
  kind: PairsKind;
  estimand: string;
  units: string;
  pairs: PairInput[];
  aba_units?: AbaUnitInput[];
  seed: number;
}

export interface PairsRequestInput {
  detail: ExperimentDetail | null;
  rows: MemberRow[];
  kind: PairsKind;
  featureKey: string;
  units: string;
  seed: number;
  signal: AbortSignal;
  valueSource: ValueSource;
  notify?: Notify;
}

export interface AbaRequest {
  kind: "aba";
  estimand: string;
  units: string;
  aba_units: AbaUnitInput[];
  seed: number;
}

export interface AbaRequestInput {
  detail: ExperimentDetail | null;
  rows: MemberRow[];
  featureKey: string;
  units: string;
  seed: number;
  signal: AbortSignal;
  valueSource: ValueSource;
}

export async function buildPairsRequest(input: PairsRequestInput): Promise<PairsRequest> {
  const groups = groupedInProtocolOrder(input.detail, input.rows);
  const left = groups[0] ?? [];
  const right = groups[1] ?? [];
  const pairs: PairInput[] = [];
  let missing = 0;
  const count = Math.min(left.length, right.length);
  for (let i = 0; i < count; i += 1) {
    const a = left[i];
    const b = right[i];
    if (!a || !b) continue;
    const [valueA, valueB] = await Promise.all([
      input.valueSource(a.sessionId, input.featureKey, input.signal),
      input.valueSource(b.sessionId, input.featureKey, input.signal),
    ]);
    if (valueA === null || valueB === null) {
      missing += 1;
      continue;
    }
    pairs.push({ unit_id: `${a.sessionId}~${b.sessionId}`, value_a: valueA, value_b: valueB });
  }
  if (missing > 0) {
    input.notify?.(
      `${String(missing)} пар(ы) пропущены: значения признака недоступны (причина: нет данных метрик).`,
      "warn",
    );
  }
  return {
    kind: input.kind,
    estimand: input.featureKey,
    units: input.units,
    pairs,
    seed: input.seed,
  };
}

export async function buildAbaRequest(input: AbaRequestInput): Promise<AbaRequest> {
  const [g1, g2, g3] = groupedInProtocolOrder(input.detail, input.rows);
  const abaUnits: AbaUnitInput[] = [];
  const count = Math.min(g1?.length ?? 0, g2?.length ?? 0, g3?.length ?? 0);
  for (let i = 0; i < count; i += 1) {
    const s1 = g1?.[i];
    const s2 = g2?.[i];
    const s3 = g3?.[i];
    if (!s1 || !s2 || !s3) continue;
    const [a1, b, a2] = await Promise.all([
      input.valueSource(s1.sessionId, input.featureKey, input.signal),
      input.valueSource(s2.sessionId, input.featureKey, input.signal),
      input.valueSource(s3.sessionId, input.featureKey, input.signal),
    ]);
    if (a1 === null || b === null || a2 === null) continue;
    abaUnits.push({ unit_id: s1.sessionId, value_a1: a1, value_b: b, value_a2: a2 });
  }
  return {
    kind: "aba",
    estimand: input.featureKey,
    units: input.units,
    aba_units: abaUnits,
    seed: input.seed,
  };
}
