/** Исполнитель расчётов панели сравнения (T11: выделено из comparisonView —
 * было 427 чистых LOC). Сборка pairs/aba-запросов, опрос statistics-runs и
 * отрисовка гейта сравнимости / конверта результата. Оркестрация (AbortController,
 * гейт lastReport, хосты) остаётся в ComparisonView — сюда передаются только
 * данные и колбэки. Без изменения поведения и математики. */

import type { LntApiClient } from "../../api/client";
import type {
  AbaUnitInput,
  ComparabilityReport,
  PairInput,
  StatisticsResultEnvelope,
} from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import type { MemberRow } from "./memberTableView";
import { renderResultPanel } from "./resultPanel";
import type { EffectView } from "./resultPanel";

export type ComparisonClient = Pick<LntApiClient, "research" | "statistics">;

/** Значение estimand по сессии; null — значение недоступно. */
export type EstimandValueSource = (
  sessionId: string,
  featureKey: string,
  signal: AbortSignal,
) => Promise<number | null>;

const POLL_INTERVAL_MS = 300;
const POLL_LIMIT = 40;

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

export async function pollStatisticsResult(
  client: ComparisonClient,
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

export interface PairsSubmitPayload {
  kind: "ab" | "repeated_blocks" | "cohort" | "longitudinal";
  estimand: string;
  units: string;
  pairs: PairInput[];
  aba_units?: AbaUnitInput[];
  seed: number;
}

export async function buildPairsPayload(
  valueSource: EstimandValueSource,
  groups: MemberRow[][],
  kind: PairsSubmitPayload["kind"],
  featureKey: string,
  units: string,
  seed: number,
  signal: AbortSignal,
  onMissing: (count: number) => void,
): Promise<PairsSubmitPayload> {
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
      valueSource(a.sessionId, featureKey, signal),
      valueSource(b.sessionId, featureKey, signal),
    ]);
    if (valueA === null || valueB === null) {
      missing += 1;
      continue;
    }
    pairs.push({ unit_id: `${a.sessionId}~${b.sessionId}`, value_a: valueA, value_b: valueB });
  }
  if (missing > 0) onMissing(missing);
  return { kind, estimand: featureKey, units, pairs, seed };
}

export interface AbaSubmitPayload {
  kind: "aba";
  estimand: string;
  units: string;
  aba_units: AbaUnitInput[];
  seed: number;
}

export async function buildAbaPayload(
  valueSource: EstimandValueSource,
  groups: MemberRow[][],
  featureKey: string,
  units: string,
  seed: number,
  signal: AbortSignal,
): Promise<AbaSubmitPayload> {
  const [g1, g2, g3] = groups;
  const abaUnits: AbaUnitInput[] = [];
  const count = Math.min(g1?.length ?? 0, g2?.length ?? 0, g3?.length ?? 0);
  for (let i = 0; i < count; i += 1) {
    const s1 = g1?.[i];
    const s2 = g2?.[i];
    const s3 = g3?.[i];
    if (!s1 || !s2 || !s3) continue;
    const [a1, b, a2] = await Promise.all([
      valueSource(s1.sessionId, featureKey, signal),
      valueSource(s2.sessionId, featureKey, signal),
      valueSource(s3.sessionId, featureKey, signal),
    ]);
    if (a1 === null || b === null || a2 === null) continue;
    abaUnits.push({ unit_id: s1.sessionId, value_a1: a1, value_b: b, value_a2: a2 });
  }
  return { kind: "aba", estimand: featureKey, units, aba_units: abaUnits, seed };
}

export function renderComparabilityOutcome(
  gateHost: HTMLElement,
  resultHost: HTMLElement,
  report: ComparabilityReport,
  onConfirmed: (message: string) => void,
): void {
  const blocks = report.findings.filter((f) => f.level === "block");
  if (!report.comparable) {
    const reason = blocks.map((f) => f.code).join(", ");
    gateHost.setAttribute("data-state", "blocked");
    gateHost.textContent = `Сравнение заблокировано проверкой сравнимости. Точная причина: ${reason}. Числовой расчёт запрещён до устранения.`;
    resultHost.replaceChildren(
      el(
        "div",
        { className: "lnt-exp-banner lnt-exp-banner-warn banner", attrs: { role: "alert" } },
        [
          el("strong", { text: "Сравнение заблокировано проверкой сравнимости." }),
          el("p", { text: `Точная причина: ${reason}. Числовой расчёт запрещён до устранения.` }),
          ...report.findings.map((f) =>
            el("p", {
              className: "lnt-exp-meta-line",
              text: `${f.dimension}: ${String(f.level)} · ${String(f.code)} · поля: ${Array.isArray(f.fields) ? (f.fields as string[]).join(", ") : String(f.fields)}`,
            }),
          ),
        ],
      ),
    );
    announcePolite("Сравнение заблокировано проверкой сравнимости");
    return;
  }
  gateHost.setAttribute("data-state", "ok");
  gateHost.textContent = `Сравнимость подтверждена (${String(report.findings.length)} измерений без блокировок). Можно запускать расчёт.`;
  onConfirmed(
    `Сравнимость подтверждена (${String(report.findings.length)} измерений без блокировок). Можно запускать расчёт.`,
  );
}

export function renderComparisonEnvelope(
  resultHost: HTMLElement,
  envelope: StatisticsResultEnvelope,
): void {
  const meta = envelope.metadata;
  if (envelope.result_kind === "refusal") {
    const reason = String((envelope.result as Record<string, unknown>).reason_code ?? "unknown");
    resultHost.replaceChildren(
      renderResultPanel({
        title: "Результат сравнения",
        effect: null,
        refusalReason: reason,
        metadata: meta,
      }),
    );
    return;
  }
  if (envelope.result_kind === "effect") {
    const effectRaw = (envelope.result as Record<string, unknown>).effect;
    const driftRaw = (envelope.result as Record<string, unknown>).drift;
    resultHost.replaceChildren(
      renderResultPanel({
        title: "Результат сравнения",
        effect: effectFromPayload(effectRaw),
        drift: driftRaw ? effectFromPayload(driftRaw) : null,
        metadata: meta,
        limitationsExtra:
          meta.estimator === "qualified_within_run_contrast"
            ? ["Квалифицированный внутрисерийный контраст: причинный вывод недоступен."]
            : [],
      }),
    );
    return;
  }
  resultHost.replaceChildren(
    renderResultPanel({
      title: "Описательный результат (без интервала)",
      effect: effectFromPayload(envelope.result),
      metadata: meta,
      limitationsExtra: ["N ниже минимума инференции: интервал не строится."],
    }),
  );
}
