/** Фикстуры T12.2: детали A/B и A/B/A с включёнными/исключёнными участниками.
 * Только тестовые данные — поведения не меняют. */

import type { Experiment } from "./views/experiments/experimentModel";
import type { ExperimentDetail } from "./views/experiments/experimentsStore";
import { proposeMember, transitionMember } from "./views/experiments/memberQc";
import type { MemberRow } from "./views/experiments/memberTableView";

function experimentOf(
  kind: "ab" | "aba",
  steps: { order: number; condition_id: string }[],
): Experiment {
  return {
    experiment_id: kind === "aba" ? "exp.t12.aba" : "exp.t12.ab",
    title: "T12",
    protocol: { kind },
    steps,
    primary_estimands: [{ feature_key: "band_mid_total" }],
  } as unknown as Experiment;
}

function row(sessionId: string, conditionId: string, order: number, excluded: boolean): MemberRow {
  const proposed = proposeMember(sessionId, "t12", "фикстура");
  const inclusion = excluded
    ? transitionMember(proposed, "excluded", "t12", "qc_corrupt_manifest")
    : transitionMember(proposed, "included", "t12", "годен");
  return {
    sessionId,
    role: `${conditionId}:${sessionId}`,
    conditionId,
    order,
    inclusion,
  } as MemberRow;
}

export function createComparisonViewFixtures(kind: "ab" | "aba"): {
  detail: ExperimentDetail;
  rows: MemberRow[];
} {
  if (kind === "aba") {
    const detail: ExperimentDetail = {
      experiment: experimentOf(kind, [
        { order: 1, condition_id: "cond_a1" },
        { order: 2, condition_id: "cond_b" },
        { order: 3, condition_id: "cond_a2" },
      ]),
      members: [],
      steps: [],
    };
    const rows: MemberRow[] = [
      row("aba-u1-a1", "cond_a1", 1, false),
      row("aba-u2-a1", "cond_a1", 2, false),
      row("aba-u1-b", "cond_b", 3, false),
      row("aba-u1-a2", "cond_a2", 4, false),
    ];
    return { detail, rows };
  }
  const detail: ExperimentDetail = {
    experiment: experimentOf(kind, [
      { order: 1, condition_id: "cond_a" },
      { order: 2, condition_id: "cond_b" },
    ]),
    members: [],
    steps: [],
  };
  const rows: MemberRow[] = [
    row("ab-u1-a", "cond_a", 1, false),
    row("ab-u1-b", "cond_b", 2, false),
    row("ab-u2-b", "cond_b", 3, false),
    row("ab-u3-b", "cond_b", 4, true),
  ];
  return { detail, rows };
}
