import { describe, expect, it } from "vitest";
import { effectFromPayload } from "./comparisonView";

/** Дисплейная логика результатов (todo 43): разбор конвертов statistics-runs
 * без any; refusal/описательный/инференциальный статусы различаются явно. */

const META = {
  units: "В²/Гц",
  sampling_unit: "measurement_session",
  hierarchy: ["site", "unit"],
  n: 4,
  missing_count: 0,
  exclusions: [],
  estimator: "qualified_within_run_contrast",
  interval_method: "seeded_block_bootstrap_percentile_95",
  provenance: { experiment_id: "exp.aba.demo", estimand: "band_mid_total", job_id: "job-1" },
};

describe("effectFromPayload / drift display", () => {
  it("extracts inferential effect with bootstrap interval bounds", () => {
    const effect = effectFromPayload({
      mean_effect: 1.9625,
      median_effect: 1.975,
      robust_effect: 1.9625,
      interval: { low: 1.6, high: 2.3125, confidence_level: 0.95 },
      stored_differences: [1.9, 2.45, 1.45, 2.05],
      metadata: {},
    });
    expect(effect).toEqual({
      mean: 1.9625,
      median: 1.975,
      robust: 1.9625,
      intervalLow: 1.6,
      intervalHigh: 2.3125,
    });
  });

  it("descriptive payload yields null interval bounds (no invented interval)", () => {
    const effect = effectFromPayload({
      mean_effect: 2.175,
      median_effect: 2.175,
      robust_effect: 2.175,
      interval: null,
      stored_differences: [1.9, 2.45],
      metadata: {},
    });
    expect(effect?.intervalLow).toBeNull();
    expect(effect?.intervalHigh).toBeNull();
  });

  it("malformed payloads return null instead of fabricated numbers", () => {
    expect(effectFromPayload(null)).toBeNull();
    expect(effectFromPayload({})).toBeNull();
    expect(effectFromPayload({ mean_effect: "1" })).toBeNull();
  });
});

describe("result envelope semantics via renderResultPanel", () => {
  it("marks descriptive status explicitly and lists limitations without causal claims", async () => {
    const { renderResultPanel } = await import("./resultPanel");
    const host = renderResultPanel({
      title: "Результат сравнения",
      effect: { mean: 2.175, median: 2.175, robust: 2.175, intervalLow: null, intervalHigh: null },
      metadata: { ...META, n: 2, interval_method: "none_insufficient_n" },
    });
    const text = host.textContent ?? "";
    expect(text).toContain("Описательная оценка без интервала");
    expect(text).toContain("N=2");
    expect(text).toContain("не является статистической уверенностью");
    // Никакой причинной лексики.
    expect(text).not.toMatch(/причинн\w+ эффект|доказыв/u);
    expect(text).toContain("причинный вывод недоступен");
  });

  it("refusal panel names the exact drift reason code and shows no numbers as contrast", async () => {
    const { renderResultPanel } = await import("./resultPanel");
    const host = renderResultPanel({
      title: "Результат сравнения",
      effect: null,
      refusalReason: "a_drift_exceeds_half_effect_or_two_sd",
      metadata: META,
    });
    const text = host.textContent ?? "";
    expect(text).toContain("a_drift_exceeds_half_effect_or_two_sd");
    expect(text).toContain("заблокирован");
    expect(text).toContain(`Единицы: ${META.units}`);
  });

  it("shows A/B/A drift separately with non-causal wording", async () => {
    const { renderResultPanel } = await import("./resultPanel");
    const host = renderResultPanel({
      title: "Результат сравнения",
      effect: {
        mean: 1.9625,
        median: 1.975,
        robust: 1.9625,
        intervalLow: 1.6,
        intervalHigh: 2.3125,
      },
      drift: { mean: 0.075, median: 0.1, robust: 0.075, intervalLow: -0.05, intervalHigh: 0.175 },
      metadata: META,
    });
    const text = host.textContent ?? "";
    expect(text).toContain("Дрейф A (A2−A1)");
    expect(text).toContain("не интерпретируется причинно");
  });
});
