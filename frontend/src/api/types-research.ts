/** Доменные типы исследовательского контура v2: эксперименты, гипотезы,
 * тренды и сравнимость (src/lnt/ui/routes_experiments.py, routes_research.py,
 * routes_quality.py, research_models.py).
 *
 * Полновесные pydantic-модели бэкенда (Experiment, ProtocolRunRecord) содержат
 * десятки вложенных полей; клиент типизирует стабильное ядро идентичности, а
 * остальную полезную нагрузку держит открытой через unknown — без any. */

export interface CursorPage<T> {
  items: T[];
  next_cursor: string | null;
}

/** Открытый JSON-объект без any: значения остаются неизвестными для клиента. */
export type OpenRecord = Record<string, unknown>;

/** Стабильное ядро эксперимента (lnt.experiments.model.Experiment). */
export interface ExperimentRecord extends OpenRecord {
  experiment_id: string;
}

export type ExperimentWritePayload = {
  experiment: ExperimentRecord;
  expected_revision: number;
};

/** Стабильное ядро гипотезы (lnt.research.Hypothesis) + status_label маршрута. */
export interface HypothesisRecord extends OpenRecord {
  schema_version: number;
  hypothesis_id: string;
  revision: number;
  statement: string;
  mechanism: string;
  status: string;
  status_label?: string;
}

export type HypothesisWritePayload = {
  hypothesis: HypothesisRecord;
  expected_revision: number;
};

export type HypothesisListQuery = {
  page_size?: number;
  cursor?: string | null;
  /** Query alias «status» на бэкенде. */
  status?: string;
};

export interface MetadataInput {
  key: string;
  value: string | number | boolean;
}

export interface ObservationInput {
  observation_id: string;
  timestamp: string | null;
  source_offset: string;
  location: string;
  condition: string;
  predictor: number | null;
  outcome: number | null;
  metadata: MetadataInput[];
}

/** Тело POST /api/v2/trends/query (TrendQuery). */
export interface TrendQueryRequest {
  observations: ObservationInput[];
  minimum_n?: number;
  max_lag?: number;
  bootstrap_samples?: number;
  seed?: number;
  units: string;
}

/** Ответ трендового анализа: известные добавленные ключи + открытые поля. */
export interface TrendAnalysisResult extends OpenRecord {
  normalized_timestamps: string[];
  metadata: {
    units: string;
    estimator: string;
    n: number;
    provenance: Record<string, unknown>;
  };
}

/** Дескриптор сессии для /api/v2/comparability/check; строгая форма живёт
 * в lnt.comparability.models.SessionDescriptor — клиент требует только id. */
export interface SessionDescriptorInput extends OpenRecord {
  session_id: string;
}

export interface ComparabilityPairRequest {
  left: SessionDescriptorInput;
  right: SessionDescriptorInput;
}

export interface ComparabilityReport {
  comparable: boolean;
  findings: OpenRecord[];
}

/** Запуск протокола (ProtocolRunRecord) — открытый конверт с ядром статуса. */
export interface ProtocolRunRecord extends OpenRecord {
  run_id: string;
  status: string;
  revision: number;
}

export type RunStartPayload = {
  run_id: string;
  mode: "real" | "simulator";
  seed?: number;
};

export type RunConfirmPayload = {
  actor: string;
  auto_confirm?: boolean;
};

/** ===== Todo 43: контракты routes_statistics.py (todo 31) ===== */

export interface PairInput {
  unit_id: string;
  value_a: number;
  value_b: number;
}

export interface AbaUnitInput {
  unit_id: string;
  value_a1: number;
  value_b: number;
  value_a2: number;
}

/** Тело POST /api/v2/experiments/{id}/statistics-runs (StatisticsRun). */
export interface StatisticsRunRequest {
  kind: "ab" | "aba" | "repeated_blocks" | "cohort" | "longitudinal";
  estimand: string;
  units: string;
  pairs?: PairInput[];
  aba_units?: AbaUnitInput[];
  seed?: number;
}

/** Снимок задачи панели (lnt/ui/job_state.py JobSnapshot.to_payload). */
export interface JobSnapshotPayload {
  schema_version: number;
  version: number;
  job_id: string;
  kind: string;
  status: string;
  stage: string;
  series_index: number | null;
  series_total: number | null;
  written_sessions: string[];
  result: OpenRecord | null;
  error_code: string | null;
  error_message: string | null;
}

/** Метаданные результата статистики (_metadata в routes_statistics.py). */
export interface StatisticsMetadata {
  units: string;
  sampling_unit: string;
  hierarchy: string[];
  n: number;
  missing_count: number;
  exclusions: { member_id: string; reason: string }[];
  estimator: string;
  interval_method: string;
  provenance: Record<string, unknown>;
}

/** Эффект (InferentialEffect/DescriptiveEffect asdict). */
export interface EffectPayload {
  mean_effect: number;
  median_effect: number;
  robust_effect: number;
  interval: { low: number; high: number; confidence_level: number } | null;
  stored_differences: number[];
  metadata: OpenRecord;
}

/** Конверт GET /statistics-runs/{job_id}/result при успехе. */
export interface StatisticsResultEnvelope {
  result_kind: "effect" | "descriptive" | "refusal";
  result: OpenRecord;
  metadata: StatisticsMetadata;
}
