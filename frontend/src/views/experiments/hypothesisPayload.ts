/** Сборка payload гипотез (C1-лист, выделен из hypothesisEditor.submitHypothesis):
 * draft → валидация → payload — дословно, вместе с зависимостью
 * hypothesisState.validate/canTransition. Автомат не дублируется. */

import type { HypothesisRecord, HypothesisWritePayload } from "../../api/types-research";
import {
  type HypothesisDraftInput,
  type HypothesisStatusValue,
  canTransition,
  validateHypothesisDraft,
} from "./hypothesisState";

/** Открытые поля HypothesisRecord (бэкенд-модель шире клиентского ядра). */
export interface HypothesisFull {
  evidence_for?: { result_id: string; result_kind: string }[];
  evidence_against?: { result_id: string; result_kind: string }[];
  linked_estimands?: { experiment_id: string; estimand: string }[];
  confounds?: string[];
  revision_history?: { revision: number; occurred_at: string; actor: string; reason: string }[];
}

export function full(record: HypothesisRecord | null): HypothesisFull {
  return (record ?? {}) as unknown as HypothesisFull;
}

const nowIso = (): string => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

export interface HypothesisPayloadInput {
  statementText: string;
  mechanismText: string;
  direction: HypothesisDraftInput["expectedDirection"];
  nextStatus: HypothesisStatusValue | "";
  link: { experimentId: string; estimand: string } | null;
}

export type HypothesisPayloadResult =
  | { ok: true; draft: HypothesisDraftInput; payload: HypothesisWritePayload }
  | { ok: false; error: string };

function draftFrom(
  record: HypothesisRecord | null,
  input: HypothesisPayloadInput,
): HypothesisDraftInput {
  return {
    hypothesisId:
      record?.hypothesis_id ??
      `h.${nowIso()
        .replaceAll(/[-:.TZ]/gu, "")
        .slice(2, 14)
        .toLowerCase()}.${Math.floor(Date.now() / 1000) % 1000}`,
    statement: input.statementText,
    mechanism: input.mechanismText,
    expectedDirection: input.direction,
    linkedEstimands:
      full(record).linked_estimands ??
      (input.link
        ? [{ experiment_id: input.link.experimentId, estimand: input.link.estimand }]
        : []),
    confounds: full(record).confounds ?? [],
    nowIso: nowIso(),
    actor: "user:operator",
  };
}

/** Дословный перенос тела submitHypothesis (draft → валидация → payload). */
export function buildHypothesisPayload(
  record: HypothesisRecord | null,
  input: HypothesisPayloadInput,
): HypothesisPayloadResult {
  const draft = draftFrom(record, input);
  const validation = validateHypothesisDraft(draft);
  if (!validation.ok) {
    return { ok: false, error: Object.values(validation.errors)[0] ?? "Проверьте поля формы." };
  }
  if (
    record !== null &&
    input.nextStatus &&
    !canTransition(record.status as HypothesisStatusValue, input.nextStatus)
  ) {
    return {
      ok: false,
      error: `Недопустимый переход статуса: ${record.status} → ${input.nextStatus}.`,
    };
  }
  const revisionHistory = full(record).revision_history ?? [
    {
      revision: 1,
      occurred_at: draft.nowIso,
      actor: draft.actor,
      reason: "создана редактором гипотез",
    },
  ];
  const payload: HypothesisWritePayload = {
    hypothesis: {
      schema_version: 1,
      hypothesis_id: draft.hypothesisId,
      revision: record?.revision ?? 1,
      statement: draft.statement.trim(),
      expected_direction: draft.expectedDirection,
      mechanism: draft.mechanism.trim(),
      linked_estimands: draft.linkedEstimands,
      confounds: draft.confounds,
      evidence_for: full(record).evidence_for ?? [],
      evidence_against: full(record).evidence_against ?? [],
      status: input.nextStatus || (record?.status ?? "draft"),
      revision_history: revisionHistory,
    },
    expected_revision: record?.revision ?? 0,
  };
  return { ok: true, draft, payload };
}
