/** Золотые числа единого мок-бэкенда (только e2e/spec, не продукт).
 *
 * Источник истины — tests/science/corpus.py (aba_effect: блоки
 * A1/B1/A2/B2, effect_size_v=0.2; правило tests/science/AGENTS.md: goldens
 * фронта зеркалят корпус и никогда не расходятся с ним). Здесь числа служат
 * КОНСТАНТАМИ: семантика aba.py (seeded_block_bootstrap, порог дрейфа) в TS
 * не дублируется — решение «эффект / отказ / описательный» принимается по
 * сигнатуре входного набора, интервал никогда не вычисляется.
 *
 * Аналитический вывод фиксированных средних из значений фикстур:
 * demo-контрасты [1.9, 2.45, 1.45, 2.05] → среднее 1.9625, медиана 1.975;
 * demo-дрейфы [0.2, 0.1, 0.1, -0.1] → среднее 0.075, медиана 0.1;
 * drift-контрасты [2.5, 3.0, 1.5, 1.5] → среднее 2.125; drift-дрейфы 3.0.
 * Интервалы — пины e2e seeded-bootstrap бэкенда, хранятся как есть. */

export const NONCE = "test-nonce-c2";
export const BUILD_ID = "c2-build";

export interface AbaFixtureValues {
  a1: number;
  b: number;
  a2: number;
}

export const ABA_FIXTURE: Record<string, AbaFixtureValues> = {
  "unit-1": { a1: 10.0, b: 12.0, a2: 10.2 },
  "unit-2": { a1: 11.0, b: 13.5, a2: 11.1 },
  "unit-3": { a1: 9.5, b: 11.0, a2: 9.6 },
  "unit-4": { a1: 10.5, b: 12.5, a2: 10.4 },
};

/** Синтетический набор с дрейфом A (a2 = a1 + 3) → гарантированный refusal. */
export const DRIFT_FIXTURE: Record<string, AbaFixtureValues> = {
  "unit-1": { a1: 10.0, b: 14.0, a2: 13.0 },
  "unit-2": { a1: 11.0, b: 15.5, a2: 14.0 },
  "unit-3": { a1: 9.5, b: 12.5, a2: 12.5 },
  "unit-4": { a1: 10.5, b: 13.5, a2: 13.5 },
};

export interface FixtureSession {
  id: string;
  label: string | null;
  health: string;
  session_type: string;
  /** Значение feature band_mid_total для valueSource. */
  metric: number;
}

export function researchSessions(): FixtureSession[] {
  const rows: FixtureSession[] = [];
  for (const [fixture, prefix] of [
    [ABA_FIXTURE, "aba"],
    [DRIFT_FIXTURE, "drift"],
  ] as const) {
    for (const [unit, values] of Object.entries(fixture)) {
      for (const cond of ["a1", "b", "a2"] as const) {
        rows.push({
          id: `${prefix}-${unit}-${cond}`,
          label: `${unit} ${cond.toUpperCase()}`,
          health: unit === "unit-4" && cond === "a2" ? "corrupt_manifest" : "ok",
          session_type: "needle",
          metric: values[cond],
        });
      }
    }
  }
  rows.push(
    {
      id: "mix-legacy-a",
      label: "Легаси A",
      health: "ok",
      session_type: "legacy",
      metric: 5,
    },
    {
      id: "mix-rc-b",
      label: "RC Б",
      health: "ok",
      session_type: "needle",
      metric: 7,
    },
  );
  return rows;
}

/** Канонические золотые интервалы (пины seeded-bootstrap бэкенда). */
export const GOLDEN_DEMO_INTERVAL = [1.5999999999999996, 2.3124999999999996] as const;
export const GOLDEN_DRIFT_INTERVAL = [-0.04999999999999982, 0.17499999999999938] as const;

/** Фиксированные золотые оценки demo-набора (аналитика выше, не расчёт). */
export const GOLDEN_DEMO_MEAN = 1.9625;
export const GOLDEN_DEMO_MEDIAN = 1.975;
export const GOLDEN_DEMO_ROBUST = 1.9625;
export const GOLDEN_DEMO_DRIFT_MEAN = 0.075;
export const GOLDEN_DEMO_DRIFT_MEDIAN = 0.1;
export const GOLDEN_DEMO_DRIFT_ROBUST = 0.075;

/** Фиксированные золотые оценки refusal-набора (аналитика выше). */
export const GOLDEN_REFUSAL_DRIFT = 3.0;
export const GOLDEN_REFUSAL_CONTRAST = 2.125;

export interface AbaUnit {
  unit_id: string;
  value_a1: number;
  value_b: number;
  value_a2: number;
}

export interface StatisticsRequest {
  kind?: unknown;
  estimand?: unknown;
  units?: unknown;
  aba_units?: AbaUnit[];
}

/** Сигнатура набора: округлённые контрастные дельты ×8. Только маршрутизация
 * к canned-ответу, не статистика: порог дрейфа aba.py здесь не считается. */
function signatureOf(units: AbaUnit[]): string {
  return units.map((u) => Math.round((u.value_b - (u.value_a1 + u.value_a2) / 2) * 8)).join(",");
}

const DEMO_SIGNATURE = "15,20,12,16";
const DRIFT_SIGNATURE = "20,24,12,12";

function contrastDiffs(units: AbaUnit[]): number[] {
  return units.map((u) => u.value_b - (u.value_a1 + u.value_a2) / 2);
}

function baseMeta(
  body: StatisticsRequest,
  experimentId: string,
  revision: number,
  jobId: string,
): Record<string, unknown> {
  return {
    units: String(body.units ?? "у.е."),
    sampling_unit: "measurement_session",
    hierarchy: ["site", "unit"],
    n: 0,
    missing_count: 0,
    exclusions: [],
    estimator: "",
    interval_method: "",
    provenance: {
      experiment_id: experimentId,
      experiment_revision: revision,
      estimand: String(body.estimand ?? ""),
      job_id: jobId,
    },
  };
}

/** Canned-конверт statistics-runs: эффект / отказ / описательный. */
export function buildStatisticsEnvelope(
  experimentId: string,
  body: StatisticsRequest,
  revision: number,
  jobId: string,
): Record<string, unknown> {
  const meta = baseMeta(body, experimentId, revision, jobId);
  if (body.kind !== "aba") {
    return {
      result_kind: "descriptive",
      result: {},
      metadata: { ...meta, n: 0, estimator: "unsupported_in_mock", interval_method: "none" },
    };
  }
  const units = body.aba_units ?? [];
  const signature = signatureOf(units);
  if (signature === DRIFT_SIGNATURE) {
    return {
      result_kind: "refusal",
      result: {
        reason_code: "a_drift_exceeds_half_effect_or_two_sd",
        drift_effect: GOLDEN_REFUSAL_DRIFT,
        contrast_effect: GOLDEN_REFUSAL_CONTRAST,
      },
      metadata: {
        ...meta,
        n: units.length,
        estimator: "qualified_within_run_contrast",
        interval_method: "blocked_by_a_drift",
      },
    };
  }
  if (signature === DEMO_SIGNATURE) {
    return {
      result_kind: "effect",
      result: {
        effect: {
          mean_effect: GOLDEN_DEMO_MEAN,
          median_effect: GOLDEN_DEMO_MEDIAN,
          robust_effect: GOLDEN_DEMO_ROBUST,
          interval: {
            low: GOLDEN_DEMO_INTERVAL[0],
            high: GOLDEN_DEMO_INTERVAL[1],
            confidence_level: 0.95,
          },
          stored_differences: contrastDiffs(units),
        },
        drift: {
          mean_effect: GOLDEN_DEMO_DRIFT_MEAN,
          median_effect: GOLDEN_DEMO_DRIFT_MEDIAN,
          robust_effect: GOLDEN_DEMO_DRIFT_ROBUST,
          interval: {
            low: GOLDEN_DRIFT_INTERVAL[0],
            high: GOLDEN_DRIFT_INTERVAL[1],
            confidence_level: 0.95,
          },
          stored_differences: units.map((u) => u.value_a2 - u.value_a1),
        },
        description_ru: "Квалифицированный внутрисерийный контраст; причинный вывод недоступен.",
      },
      metadata: {
        ...meta,
        n: units.length,
        estimator: "qualified_within_run_contrast",
        interval_method: "seeded_block_bootstrap_percentile_95",
      },
    };
  }
  // Вне канонических наборов интервал не выдумываем и медианы не считаем:
  // честный описательный результат (семантика бэкенда DescriptiveEffect).
  return {
    result_kind: "descriptive",
    result: {
      mean_effect: null,
      median_effect: null,
      robust_effect: null,
      interval: null,
      stored_differences: contrastDiffs(units),
    },
    metadata: {
      ...meta,
      n: units.length,
      estimator: "qualified_within_run_contrast",
      interval_method: "none_insufficient_n",
    },
  };
}
