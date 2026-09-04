/** TDD RED (очередь C2): золотые числа единого мока — только константы
 * из tests/science/corpus.py (aba_effect), без дублирования семантики aba.py
 * в TS: ни bootstrap-интервалов, ни порога дрейфа в коде — решение по
 * сигнатуре набора, числа фиксированы. */

import { describe, expect, it } from "vitest";
import {
  ABA_FIXTURE,
  DRIFT_FIXTURE,
  GOLDEN_DEMO_INTERVAL,
  GOLDEN_DRIFT_INTERVAL,
  buildStatisticsEnvelope,
} from "./mockGolden";

function demoUnits(): { unit_id: string; value_a1: number; value_b: number; value_a2: number }[] {
  return Object.entries(ABA_FIXTURE).map(([unit, values]) => ({
    unit_id: unit,
    value_a1: values.a1,
    value_b: values.b,
    value_a2: values.a2,
  }));
}

function driftUnits(): { unit_id: string; value_a1: number; value_b: number; value_a2: number }[] {
  return Object.entries(DRIFT_FIXTURE).map(([unit, values]) => ({
    unit_id: unit,
    value_a1: values.a1,
    value_b: values.b,
    value_a2: values.a2,
  }));
}

describe("единый мок: золотые числа ABA", () => {
  it("канонический demo-набор даёт инференциальный конверт с золотом", () => {
    const envelope = buildStatisticsEnvelope(
      "exp.aba.demo",
      { kind: "aba", aba_units: demoUnits() },
      1,
      "job-1",
    );
    expect(envelope.result_kind).toBe("effect");
    const result = envelope.result as Record<
      string,
      Record<string, number | Record<string, number>>
    >;
    const effect = result.effect as Record<string, number | Record<string, number>>;
    expect(effect.mean_effect).toBeCloseTo(1.9625, 10);
    expect(effect.median_effect).toBeCloseTo(1.975, 10);
    expect(effect.robust_effect).toBeCloseTo(1.9625, 10);
    const interval = effect.interval as Record<string, number>;
    expect(interval.low).toBe(GOLDEN_DEMO_INTERVAL[0]);
    expect(interval.high).toBe(GOLDEN_DEMO_INTERVAL[1]);
    const drift = result.drift as Record<string, number | Record<string, number>>;
    expect(drift.mean_effect).toBeCloseTo(0.075, 10);
    const driftInterval = drift.interval as Record<string, number>;
    expect(driftInterval.low).toBe(GOLDEN_DRIFT_INTERVAL[0]);
    expect(driftInterval.high).toBe(GOLDEN_DRIFT_INTERVAL[1]);
    const meta = envelope.metadata as Record<string, unknown>;
    expect(meta.n).toBe(4);
    expect(meta.estimator).toBe("qualified_within_run_contrast");
    expect(meta.interval_method).toBe("seeded_block_bootstrap_percentile_95");
  });

  it("дрейфовый набор даёт refusal с кодом, без выдуманного интервала", () => {
    const envelope = buildStatisticsEnvelope(
      "exp.aba.drift",
      { kind: "aba", aba_units: driftUnits() },
      1,
      "job-1",
    );
    expect(envelope.result_kind).toBe("refusal");
    const result = envelope.result as Record<string, unknown>;
    expect(result.reason_code).toBe("a_drift_exceeds_half_effect_or_two_sd");
    expect(result.drift_effect).toBeCloseTo(3.0, 10);
    expect(result.contrast_effect).toBeCloseTo(2.125, 10);
    expect("interval" in result).toBe(false);
  });

  it("неканонический набор даёт описательный результат без интервала и без выдуманных медиан", () => {
    const envelope = buildStatisticsEnvelope(
      "exp.aba.lown",
      { kind: "aba", aba_units: demoUnits().slice(0, 2) },
      1,
      "job-1",
    );
    expect(envelope.result_kind).toBe("descriptive");
    const result = envelope.result as Record<string, unknown>;
    expect(result.interval).toBeNull();
    expect(result.median_effect).toBeNull();
    expect(result.robust_effect).toBeNull();
    const meta = envelope.metadata as Record<string, unknown>;
    expect(meta.n).toBe(2);
    expect(meta.interval_method).toBe("none_insufficient_n");
  });

  it("не-ABA kind даёт описательный результат без статистики", () => {
    const envelope = buildStatisticsEnvelope("exp.mix", { kind: "ab", aba_units: [] }, 1, "job-1");
    expect(envelope.result_kind).toBe("descriptive");
    const meta = envelope.metadata as Record<string, unknown>;
    expect(meta.estimator).toBe("unsupported_in_mock");
  });
});
