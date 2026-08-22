import { describe, expect, it } from "vitest";
import {
  STATUS_LABELS_RU,
  canTransition,
  isValidEvidence,
  nextStatuses,
  validateHypothesisDraft,
} from "./hypothesisState";

describe("hypothesisState (todo 43)", () => {
  it("allows only the backend status workflow draft → testing → verdicts", () => {
    expect(canTransition("draft", "testing")).toBe(true);
    expect(canTransition("draft", "consistent_with_observations")).toBe(false);
    expect(canTransition("testing", "consistent_with_observations")).toBe(true);
    expect(canTransition("testing", "not_consistent")).toBe(true);
    expect(canTransition("testing", "inconclusive")).toBe(true);
    // Терминальные вердикты не переходят никуда, кроме возврата в testing из inconclusive.
    expect(canTransition("consistent_with_observations", "testing")).toBe(false);
    expect(canTransition("not_consistent", "draft")).toBe(false);
    expect(canTransition("inconclusive", "testing")).toBe(true);
  });

  it("nextStatuses mirrors the transition map and labels are non-causal Russian", () => {
    expect(nextStatuses("draft")).toEqual(["testing"]);
    expect(nextStatuses("consistent_with_observations")).toEqual([]);
    expect(STATUS_LABELS_RU.consistent_with_observations).toContain("согласуется");
    expect(Object.values(STATUS_LABELS_RU).join(" ")).not.toMatch(/доказа|причин/u);
  });

  it("evidence references must be result_id + descriptive_* kind (no fabricated evidence)", () => {
    expect(isValidEvidence({ result_id: "job-1", result_kind: "descriptive_statistic_run" })).toBe(
      true,
    );
    expect(isValidEvidence({ result_id: "job-1", result_kind: "inferential_effect" })).toBe(false);
    expect(isValidEvidence({ result_id: "", result_kind: "descriptive_x" })).toBe(false);
  });

  it("validates drafts with Russian field errors before any network call", () => {
    const bad = validateHypothesisDraft({
      hypothesisId: "Плохой Id",
      statement: "",
      mechanism: "",
      expectedDirection: "increase",
      linkedEstimands: [],
      confounds: [],
      nowIso: "2026-08-22T00:00:00Z",
      actor: "operator",
    });
    expect(bad.ok).toBe(false);
    expect(bad.errors.hypothesisId).toBeTruthy();
    expect(bad.errors.statement).toBeTruthy();
    expect(bad.errors.linked).toBeTruthy();
    expect(bad.errors.actor).toContain("user:");

    const good = validateHypothesisDraft({
      hypothesisId: "h.test.1",
      statement: "Экранирование снижает фон",
      mechanism: "экранированный кабель",
      expectedDirection: "decrease",
      linkedEstimands: [{ experiment_id: "exp.1", estimand: "band_mid_total" }],
      confounds: ["температура"],
      nowIso: "2026-08-22T00:00:00Z",
      actor: "user:operator",
    });
    expect(good.ok).toBe(true);
  });
});
