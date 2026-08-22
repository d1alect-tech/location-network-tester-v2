/** Статусный автомат гипотез (todo 43): допустимые переходы по контракту
 * lnt/research/hypothesis_models.py. Формулировки статусов неcausal —
 * «согласуется с наблюдениями», а не «доказана». */

export type HypothesisStatusValue =
  | "draft"
  | "testing"
  | "consistent_with_observations"
  | "not_consistent"
  | "inconclusive";

const TRANSITIONS: Record<HypothesisStatusValue, readonly HypothesisStatusValue[]> = {
  draft: ["testing"],
  testing: ["consistent_with_observations", "not_consistent", "inconclusive"],
  consistent_with_observations: [],
  not_consistent: [],
  inconclusive: ["testing"],
};

export const STATUS_LABELS_RU: Record<HypothesisStatusValue, string> = {
  draft: "черновик",
  testing: "проверяется",
  consistent_with_observations: "согласуется с наблюдениями",
  not_consistent: "не согласуется с наблюдениями",
  inconclusive: "недостаточно данных",
};

export function canTransition(from: HypothesisStatusValue, to: HypothesisStatusValue): boolean {
  return TRANSITIONS[from]?.includes(to) ?? false;
}

export function nextStatuses(from: HypothesisStatusValue): readonly HypothesisStatusValue[] {
  return TRANSITIONS[from] ?? [];
}

/** Evidence-ссылка бэкенда: result_kind обязан начинаться с descriptive_. */
export const EVIDENCE_KIND_PATTERN = /^descriptive_/;

export interface EvidenceReference {
  result_id: string;
  result_kind: string;
}

export function isValidEvidence(reference: EvidenceReference): boolean {
  return reference.result_id.length > 0 && EVIDENCE_KIND_PATTERN.test(reference.result_kind);
}

/** Собирает payload новой гипотезы (schema 1) с цепочкой revision_history. */
export interface HypothesisDraftInput {
  hypothesisId: string;
  statement: string;
  mechanism: string;
  expectedDirection: "increase" | "decrease" | "no_direction";
  linkedEstimands: { experiment_id: string; estimand: string }[];
  confounds: string[];
  nowIso: string;
  actor: string;
}

interface DraftCheck {
  ok: boolean;
  errors: Record<string, string>;
}

export function validateHypothesisDraft(input: HypothesisDraftInput): DraftCheck {
  const errors: Record<string, string> = {};
  if (!/^[a-z0-9._-]+$/.test(input.hypothesisId)) {
    errors.hypothesisId = "Идентификатор: строчные латинские буквы, цифры, точка, дефис.";
  }
  if (input.statement.trim().length === 0) errors.statement = "Формулировка обязательна.";
  if (input.mechanism.trim().length === 0) errors.mechanism = "Механизм обязателен.";
  if (input.linkedEstimands.length === 0) errors.linked = "Нужна ссылка на estimand эксперимента.";
  if (!/^user:/.test(input.actor)) errors.actor = "Актор должен иметь префикс user:";
  return { ok: Object.keys(errors).length === 0, errors };
}
