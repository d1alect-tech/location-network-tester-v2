import { describe, expect, it } from "vitest";
import {
  type ReportDraft,
  type ReportEffectNumbers,
  composeReportMarkdown,
  deriveLimitations,
} from "./reportModel";

const SAMPLE_EFFECT: ReportEffectNumbers = {
  mean_effect: 1.9625,
  median_effect: 1.9,
  robust_effect: 1.95,
  interval_low: 1.6,
  interval_high: 2.3125,
  confidence_level: 0.95,
};

function draftBase(): ReportDraft {
  return {
    title: "Синтетика exp.aba.demo",
    provenance: {
      experiment_id: "exp.aba.demo",
      experiment_revision: 3,
      estimand: "band_mid_total",
      job_id: "job-7",
      generated_at: "2026-08-22T10:00:00Z",
    },
    core: {
      units: "В²/Гц",
      sampling_unit: "measurement_session",
      hierarchy: ["site", "unit"],
      n: 4,
      missing_count: 0,
      exclusions: [],
      estimator: "qualified_within_run_contrast",
      interval_method: "seeded_block_bootstrap_percentile_95",
    },
    outcome: {
      kind: "effect",
      effect: SAMPLE_EFFECT,
      drift: null,
    },
    planes: [
      { session_id: "s1", available: true, reason_code: null, model_kind: "rc_shunt_v1" },
      { session_id: "s2", available: true, reason_code: null, model_kind: "rc_shunt_v1" },
    ],
    recipes: [{ recipe_id: "rec-1", name: "Базовый спектр", sha256: "a".repeat(64) }],
    limitations: [],
  };
}

describe("deriveLimitations", () => {
  it("clean inferential report keeps only the non-causal limitation", () => {
    const limitations = deriveLimitations({
      outcome: { kind: "effect", effect: SAMPLE_EFFECT, drift: null },
      core: draftBase().core,
      planes: draftBase().planes,
      unhealthySessions: [],
      recipesLinked: true,
    });
    expect(limitations.map((item) => item.code)).toEqual(["causal_inference_not_available"]);
  });

  it("descriptive outcome yields the no-interval limitation with Russian detail", () => {
    const limitations = deriveLimitations({
      outcome: {
        kind: "descriptive",
        effect: {
          mean_effect: 1,
          median_effect: 1,
          robust_effect: 1,
          interval_low: null,
          interval_high: null,
        },
      },
      core: draftBase().core,
      planes: [],
      unhealthySessions: [],
      recipesLinked: false,
    });
    const codes = limitations.map((item) => item.code);
    expect(codes).toContain("descriptive_no_interval");
    expect(codes).toContain("recipes_unlinked");
    const descriptive = limitations.find((item) => item.code === "descriptive_no_interval");
    expect(descriptive?.detail).toContain("не является статистической уверенностью");
  });

  it("refusal carries the exact reason code and suppresses causal boilerplate", () => {
    const limitations = deriveLimitations({
      outcome: { kind: "refusal", reason_code: "a_drift_exceeds_half_effect_or_two_sd" },
      core: draftBase().core,
      planes: [],
      unhealthySessions: [],
      recipesLinked: true,
    });
    const refusal = limitations.find((item) => item.code === "statistics_refusal");
    expect(refusal?.detail).toContain("a_drift_exceeds_half_effect_or_two_sd");
    expect(limitations.map((item) => item.code)).not.toContain("causal_inference_not_available");
  });

  it("missing values, exclusions, unavailable planes and unhealthy sessions are each reported", () => {
    const limitations = deriveLimitations({
      outcome: { kind: "effect", effect: SAMPLE_EFFECT, drift: null },
      core: {
        ...draftBase().core,
        missing_count: 2,
        exclusions: [{ member_id: "m-9", reason: "qc_corrupt_manifest" }],
      },
      planes: [
        { session_id: "s1", available: false, reason_code: "manifest_schema_v1", model_kind: null },
      ],
      unhealthySessions: [{ session_id: "s-bad", health: "corrupt_manifest" }],
      recipesLinked: true,
    });
    const codes = limitations.map((item) => item.code);
    expect(codes).toContain("missing_values");
    expect(codes).toContain("qc_exclusions");
    expect(codes).toContain("input_reference_unavailable");
    expect(codes).toContain("unhealthy_sessions_excluded");
    const planes = limitations.find((item) => item.code === "input_reference_unavailable");
    expect(planes?.detail).toContain("manifest_schema_v1");
  });
});

describe("composeReportMarkdown", () => {
  it("renders provenance, units/N, estimator, planes and limitations sections", () => {
    const base = draftBase();
    const markdown = composeReportMarkdown({
      ...base,
      limitations: deriveLimitations({
        outcome: base.outcome,
        core: base.core,
        planes: base.planes,
        unhealthySessions: [],
        recipesLinked: true,
      }),
    });
    expect(markdown).toContain("# Отчёт: Синтетика exp.aba.demo");
    expect(markdown).toContain("exp.aba.demo");
    expect(markdown).toContain("job-7");
    expect(markdown).toContain("В²/Гц");
    expect(markdown).toContain("N = 4");
    expect(markdown).toContain("sampling_unit: measurement_session");
    expect(markdown).toContain("qualified_within_run_contrast");
    expect(markdown).toContain("[1.6000; 2.3125]");
    expect(markdown).toContain("## Плоскости измерения");
    expect(markdown).toContain("## Рецепты анализа");
    expect(markdown).toContain("## Ограничения");
    expect(markdown).toContain("causal_inference_not_available");
  });

  it("markdown escapes pipe characters so table structure cannot be corrupted by data", () => {
    const markdown = composeReportMarkdown({
      ...draftBase(),
      title: "Опыт | с пайпом",
    });
    expect(markdown).toContain("Опыт \\| с пайпом");
  });
});
