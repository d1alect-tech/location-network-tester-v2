import { describe, expect, it } from "vitest";
import {
  buildAbaRequest,
  buildPairsRequest,
  groupedInProtocolOrder,
  includedByCondition,
  orderedConditions,
} from "./comparisonRequests";
import type { ExperimentDetail } from "./experimentsStore";
import { proposeMember, transitionMember } from "./memberQc";
import type { MemberRow } from "./memberTableView";

function row(sessionId: string, conditionId: string, order: number, excluded = false): MemberRow {
  const proposed = proposeMember(sessionId, "test", "init");
  return {
    sessionId,
    role: `${conditionId}:${sessionId}`,
    conditionId,
    order,
    health: "ok",
    verdict: { tone: "ok", label: "QC пройден", recommended_state: null, reason_code: null },
    inclusion: excluded ? transitionMember(proposed, "excluded", "test", "qc_manual") : proposed,
  };
}

function detailWithSteps(conditions: string[]): ExperimentDetail {
  return {
    experiment: {
      experiment_id: "exp.test",
      protocol: { kind: "ab" },
      steps: conditions.map((condition_id, index) => ({
        order: index + 1,
        condition_id,
        instruction: `Шаг ${String(index + 1)}`,
      })),
    },
    members: [],
    steps: [],
  } as unknown as ExperimentDetail;
}

describe("comparisonRequests grouping", () => {
  it("excludes rejected members and sorts by order", () => {
    const rows = [row("s2", "cond_b", 2), row("s1", "cond_a", 1), row("sx", "cond_a", 0, true)];
    const map = includedByCondition(rows);
    expect(map.get("cond_a")?.map((r) => r.sessionId)).toEqual(["s1"]);
    expect(map.get("cond_b")?.map((r) => r.sessionId)).toEqual(["s2"]);
  });

  it("orders conditions by protocol steps, not alphabet", () => {
    const detail = detailWithSteps(["cond_b", "cond_a"]);
    expect(orderedConditions(detail)).toEqual(["cond_b", "cond_a"]);
    expect(orderedConditions(null)).toEqual([]);
  });

  it("groups included rows in protocol order", () => {
    const detail = detailWithSteps(["cond_a", "cond_b"]);
    const rows = [row("s2", "cond_b", 1), row("s1", "cond_a", 1)];
    const groups = groupedInProtocolOrder(detail, rows);
    expect(groups.map((g) => g.map((r) => r.sessionId))).toEqual([["s1"], ["s2"]]);
  });
});

describe("comparisonRequests builders", () => {
  it("builds B-A pairs and warns about missing values byte-identically", async () => {
    const detail = detailWithSteps(["cond_a", "cond_b"]);
    const rows = [
      row("a1", "cond_a", 1),
      row("a2", "cond_a", 2),
      row("b1", "cond_b", 1),
      row("b2", "cond_b", 2),
    ];
    const notes: string[] = [];
    const values = new Map([
      ["a1", 10],
      ["b1", 14],
      ["a2", 11],
    ]);
    const request = await buildPairsRequest({
      detail,
      rows,
      kind: "ab",
      featureKey: "band_mid_total",
      units: "В²/Гц",
      seed: 43,
      signal: new AbortController().signal,
      valueSource: async (sessionId) => values.get(sessionId) ?? null,
      notify: (message) => {
        notes.push(message);
      },
    });
    expect(request.pairs).toEqual([{ unit_id: "a1~b1", value_a: 10, value_b: 14 }]);
    expect(request.estimand).toBe("band_mid_total");
    expect(notes).toEqual([
      "1 пар(ы) пропущены: значения признака недоступны (причина: нет данных метрик).",
    ]);
  });

  it("builds ABA units in protocol order", async () => {
    const detail = detailWithSteps(["cond_a1", "cond_b", "cond_a2"]);
    const rows = [row("a1", "cond_a1", 1), row("b1", "cond_b", 1), row("a2", "cond_a2", 1)];
    const request = await buildAbaRequest({
      detail,
      rows,
      featureKey: "band_mid_total",
      units: "В²/Гц",
      seed: 43,
      signal: new AbortController().signal,
      valueSource: async () => 1,
    });
    expect(request.kind).toBe("aba");
    expect(request.aba_units).toHaveLength(1);
  });
});
