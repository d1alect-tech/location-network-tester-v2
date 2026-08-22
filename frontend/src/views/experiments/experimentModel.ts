/** Модель эксперимента v2 (todo 43): зеркало строгой схемы
 * lnt/experiments/model.py + values.py (schema 1, extra=forbid).
 * Клиент строит только валидные payload-ы: любые поля, которых бэкенд
 * не примет, отсекаются здесь, а не на сервере. */

import type { OpenRecord } from "../../api/types-research";

export type ProtocolKind = "ab" | "aba" | "repeated_blocks" | "cohort" | "longitudinal";
export type ExperimentStatus = "draft" | "active" | "completed" | "archived";
export type MultiplicityPolicy = "none" | "holm" | "bonferroni" | "fdr_bh";

export interface Factor {
  factor_id: string;
  kind: "categorical" | "continuous" | "boolean";
  levels: (string | number | boolean)[];
}

export interface Condition {
  condition_id: string;
  values: { factor_id: string; value: string | number | boolean }[];
}

export interface ProtocolDeclaration {
  kind: ProtocolKind;
  sampling_unit: string;
  site_key: string;
  subject_key: string;
  block_key: string;
  pairing_key: string;
  assignment_scheme: string;
  order_scheme: string;
  within_unit_aggregation: string;
  independence_assumptions: string[];
  minimum_n: number;
  multiplicity_policy: MultiplicityPolicy;
}

export interface ProtocolStep {
  order: number;
  condition_id: string;
  instruction: string;
}

/** Member бэкенда не содержит exclusion — состояние включённости живёт
 * в memberQc.ts (клиентский append-only журнал, семантика state.py). */
export interface ExperimentMember extends OpenRecord {
  session_id: string;
  storage_ref: string;
  role: string;
  condition_id: string;
  order: number;
  block_key?: string | null;
  pairing_key?: string | null;
}

export interface Estimand {
  feature_key: string;
  direction: "increase" | "decrease" | "two_sided";
  contrast: string;
}

export interface ConfoundCheck {
  key: string;
  checked: boolean;
  note?: string | null;
}

export interface RevisionRecord {
  revision: number;
  occurred_at: string;
  actor: string;
  reason: string;
}

/** Стабильное ядро Experiment (schema 1); остальное — открытые поля. */
export interface Experiment extends OpenRecord {
  experiment_schema_version: number;
  experiment_id: string;
  title: string;
  question: string;
  status: ExperimentStatus;
  revision: number;
  factors: Factor[];
  conditions: Condition[];
  protocol: ProtocolDeclaration;
  steps: ProtocolStep[];
  members: ExperimentMember[];
  interventions: OpenRecord[];
  primary_estimands: Estimand[];
  secondary_estimands: Estimand[];
  confound_checklist: ConfoundCheck[];
  revision_history: RevisionRecord[];
}

export const EXPERIMENT_ID_PATTERN = /^[a-z0-9._-]+$/;

const PROTOCOL_LABELS: Record<ProtocolKind, string> = {
  ab: "A/B",
  aba: "A/B/A",
  repeated_blocks: "Повторные блоки",
  cohort: "Когорта",
  longitudinal: "Продольный ряд",
};

export function protocolLabel(kind: string): string {
  return PROTOCOL_LABELS[kind as ProtocolKind] ?? kind;
}

export interface DraftExperimentInput {
  experimentId: string;
  title: string;
  question: string;
  kind: ProtocolKind;
  /** Сессии-участники по условиям; порядок = order участника. */
  sessionsByCondition: Record<string, { session_id: string; storage_ref: string }[]>;
  estimandKey: string;
  units: string;
  minimumN: number;
  nowIso: string;
  actor: string;
}

interface DraftValidation {
  ok: boolean;
  errors: Record<string, string>;
}

/** Валидация черновика ДО отправки: русские сообщения по полям. */
export function validateDraft(input: DraftExperimentInput): DraftValidation {
  const errors: Record<string, string> = {};
  if (!EXPERIMENT_ID_PATTERN.test(input.experimentId)) {
    errors.experimentId = "Идентификатор: строчные латинские буквы, цифры, точка, дефис.";
  }
  if (input.title.trim().length === 0) errors.title = "Название обязательно.";
  if (input.question.trim().length === 0) errors.question = "Вопрос исследования обязателен.";
  if (input.estimandKey.trim().length === 0) errors.estimandKey = "Укажите оцениваемый признак.";
  if (!Number.isFinite(input.minimumN) || input.minimumN < 2) {
    errors.minimumN = "Минимальный N ≥ 2.";
  }
  const conditions = Object.entries(input.sessionsByCondition);
  if (conditions.length < 2) errors.sessions = "Нужно минимум два условия с сессиями.";
  for (const [, sessions] of conditions) {
    if (sessions.length === 0) errors.sessions = "Каждое условие требует хотя бы одну сессию.";
  }
  return { ok: Object.keys(errors).length === 0, errors };
}

const PROTOCOL_PRESETS: Record<
  "ab" | "aba" | "repeated_blocks",
  Pick<ProtocolDeclaration, "assignment_scheme" | "order_scheme">
> = {
  ab: {
    assignment_scheme: "alternating_by_block",
    order_scheme: "fixed_ab_order",
  },
  aba: {
    assignment_scheme: "within_unit_aba_sequence",
    order_scheme: "aba_within_unit",
  },
  repeated_blocks: {
    assignment_scheme: "blocked_randomized",
    order_scheme: "block_counterbalanced",
  },
};

/** Собирает полный Experiment (schema 1) из проверенного черновика.
 * Условия A/B и A/B/A фиксированы доменом; шаги протокола упорядочены. */
export function buildExperimentDraft(input: DraftExperimentInput): Experiment {
  const validation = validateDraft(input);
  if (!validation.ok) throw new Error("черновик эксперимента не прошёл валидацию");
  const conditionIds = Object.keys(input.sessionsByCondition);
  const factorId = `${input.kind}_factor`;
  const conditions: Condition[] = conditionIds.map((conditionId) => ({
    condition_id: conditionId,
    values: [{ factor_id: factorId, value: conditionId }],
  }));
  const steps: ProtocolStep[] =
    input.kind === "aba"
      ? ["cond_a1", "cond_b", "cond_a2"].map((conditionId, index) => ({
          order: index + 1,
          condition_id: conditionIds[index] ?? conditionId,
          instruction: `Шаг ${index + 1}: измерение условия ${conditionIds[index] ?? conditionId}`,
        }))
      : conditionIds.map((conditionId, index) => ({
          order: index + 1,
          condition_id: conditionId,
          instruction: `Шаг ${index + 1}: измерение условия ${conditionId}`,
        }));
  const members: ExperimentMember[] = [];
  let order = 1;
  for (const [conditionId, sessions] of Object.entries(input.sessionsByCondition)) {
    for (const session of sessions) {
      members.push({
        session_id: session.session_id,
        storage_ref: session.storage_ref,
        role: `${conditionId}:${session.session_id}`,
        condition_id: conditionId,
        order,
        block_key: null,
        pairing_key: null,
      });
      order += 1;
    }
  }
  return {
    experiment_schema_version: 1,
    experiment_id: input.experimentId,
    title: input.title.trim(),
    question: input.question.trim(),
    status: "draft",
    revision: 1,
    factors: [{ factor_id: factorId, kind: "categorical", levels: conditionIds }],
    conditions,
    protocol: {
      kind: input.kind,
      sampling_unit: "measurement_session",
      site_key: "site",
      subject_key: "unit",
      block_key: "block",
      pairing_key: "pairing",
      assignment_scheme:
        PROTOCOL_PRESETS[input.kind as "ab" | "aba" | "repeated_blocks"]?.assignment_scheme ??
        "descriptive_no_assignment",
      order_scheme:
        PROTOCOL_PRESETS[input.kind as "ab" | "aba" | "repeated_blocks"]?.order_scheme ??
        "observation_order",
      within_unit_aggregation: "mean_of_repeats",
      independence_assumptions: ["independent_units"],
      minimum_n: Math.trunc(input.minimumN),
      multiplicity_policy: "none",
    },
    steps,
    members,
    interventions: [],
    primary_estimands: [
      { feature_key: input.estimandKey.trim(), direction: "two_sided", contrast: "b_minus_a" },
    ],
    secondary_estimands: [],
    confound_checklist: [],
    revision_history: [
      {
        revision: 1,
        occurred_at: input.nowIso,
        actor: input.actor,
        reason: "создан мастер создания",
      },
    ],
  };
}
