import { describe, expect, it } from "vitest";
import { buildExperimentDraft } from "./experimentModel";

describe("buildExperimentDraft", () => {
  it("uses the backend's neutral estimand direction", () => {
    const experiment = buildExperimentDraft({
      experimentId: "exp.real",
      title: "Реальный эксперимент",
      question: "Есть ли измеримое различие?",
      kind: "ab",
      sessionsByCondition: {
        cond_a: [{ session_id: "a1", storage_ref: "a1" }],
        cond_b: [{ session_id: "b1", storage_ref: "b1" }],
      },
      estimandKey: "needle_mean_v",
      units: "V",
      minimumN: 2,
      nowIso: "2026-09-09T00:00:00Z",
      actor: "test",
    });

    expect(experiment.primary_estimands[0]?.direction).toBe("descriptive");
  });
});
