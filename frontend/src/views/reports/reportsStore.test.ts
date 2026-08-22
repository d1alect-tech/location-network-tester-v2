import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "../../api/client";
import type { StatisticsResultEnvelope, StatisticsRunRequest } from "../../api/types-research";
import type { ExperimentDetail } from "../experiments/experimentsStore";
import { ReportsStore } from "./reportsStore";

type ClientStub = Pick<
  LntApiClient,
  "research" | "statistics" | "plots" | "catalogSessions" | "analysis"
>;

const UNITS = "В²/Гц";
const CONDITIONS = ["cond_a1", "cond_b", "cond_a2"] as const;
const UNITS_ABA = ["u1", "u2"] as const;

function abaDetail(): ExperimentDetail {
  const members = [];
  const steps = CONDITIONS.map((condition, index) => ({
    order: index + 1,
    condition_id: condition,
    instruction: `шаг ${index + 1}`,
  }));
  let order = 1;
  for (const unit of UNITS_ABA) {
    for (const condition of CONDITIONS) {
      members.push({
        session_id: `${unit}-${condition}`,
        storage_ref: `${unit}-${condition}`,
        role: `${condition}:${unit}`,
        condition_id: condition,
        order,
      });
      order += 1;
    }
  }
  return {
    experiment: {
      experiment_id: "exp.demo",
      title: "Демо A/B/A",
      revision: 2,
      protocol: { kind: "aba" },
      primary_estimands: [{ feature_key: "band_mid_total" }],
      steps,
    },
    members,
    steps,
  } as unknown as ExperimentDetail;
}

function effectEnvelope(): StatisticsResultEnvelope {
  return {
    result_kind: "effect",
    result: {
      effect: {
        mean_effect: 2,
        median_effect: 2,
        robust_effect: 2,
        interval: { low: 1.5, high: 2.5, confidence_level: 0.95 },
        stored_differences: [2],
      },
      drift: null,
    },
    metadata: {
      units: UNITS,
      sampling_unit: "measurement_session",
      hierarchy: ["site", "unit"],
      n: 2,
      missing_count: 0,
      exclusions: [],
      estimator: "qualified_within_run_contrast",
      interval_method: "seeded_block_bootstrap_percentile_95",
      provenance: { experiment_id: "exp.demo", estimand: "band_mid_total", job_id: "job-1" },
    },
  };
}

interface StubOptions {
  health?: Map<string, string>;
  planeStatus?: string;
  recipesFail?: boolean;
  /** Сессии, для которых plots.detail падает (значение недоступно). */
  failDetailFor?: string[];
}

function clientStub(
  envelope: StatisticsResultEnvelope,
  options: StubOptions = {},
): ClientStub & {
  submitted: StatisticsRunRequest[];
} {
  const submitted: StatisticsRunRequest[] = [];
  const planeStatus = options.planeStatus ?? "available";
  const failing = new Set(options.failDetailFor ?? []);
  return {
    submitted,
    research: {} as ClientStub["research"],
    statistics: {
      submit: vi.fn(async (_experimentId: string, request: StatisticsRunRequest) => {
        submitted.push(request);
        return {
          schema_version: 1,
          version: 1,
          job_id: "job-1",
          kind: "research_analysis",
          status: "queued",
          stage: "queued",
          series_index: null,
          series_total: null,
          written_sessions: [],
          result: null,
          error_code: null,
          error_message: null,
        };
      }),
      result: vi.fn(async () => envelope),
    } as ClientStub["statistics"],
    plots: {
      detail: vi.fn(async (sessionId: string) => {
        if (failing.has(sessionId)) throw new Error("detail unavailable");
        return {
          name: sessionId,
          manifest: {},
          analysis: {
            metrics: { band_mid_total: 10 },
            ch1_input_reference:
              planeStatus === "available"
                ? { status: "available", model_kind: "rc_shunt_v1" }
                : { status: "unavailable", reason_code: planeStatus },
          },
          spectrum_available: true,
          waveform_available: false,
          ch2_available: false,
        };
      }),
    } as unknown as ClientStub["plots"],
    catalogSessions: vi.fn(async () => ({
      items: [...(options.health ?? new Map<string, string>()).entries()].map(([id, health]) => ({
        id,
        health,
      })),
      next_cursor: null,
    })) as unknown as ClientStub["catalogSessions"],
    analysis: {
      recipes: options.recipesFail
        ? vi.fn(async () => {
            throw new Error("recipes unavailable");
          })
        : vi.fn(async () => [
            { recipe_id: "rec-1", name: "Базовый", sha256: "a".repeat(64), recipe: {} },
          ]),
    } as unknown as ClientStub["analysis"],
  };
}

function fullHealth(extra: Record<string, string> = {}): Map<string, string> {
  const health = new Map<string, string>();
  for (const unit of UNITS_ABA)
    for (const condition of CONDITIONS) health.set(`${unit}-${condition}`, "ok");
  for (const [id, value] of Object.entries(extra)) health.set(id, value);
  return health;
}

describe("ReportsStore.buildReport", () => {
  it("includes members despite QC health notes; records them as typed limitations", async () => {
    // Семантика рабочей области экспериментов: включение — решение оператора,
    // health — вердикт на экране. Значение доступно → участник в расчёте.
    const client = clientStub(effectEnvelope(), {
      health: fullHealth({ "u1-cond_a2": "corrupt_manifest" }),
    });
    const store = new ReportsStore({ client: client as unknown as LntApiClient });
    const { draft, markdown } = await store.buildReport(abaDetail());

    expect(draft.outcome.kind).toBe("effect");
    expect(client.submitted).toHaveLength(1);
    const request = client.submitted[0];
    if (request === undefined) throw new Error("запрос статистики не зафиксирован");
    if (request.kind !== "aba") throw new Error(`ожидался aba, получен ${request.kind}`);
    expect(request.aba_units).toHaveLength(2);
    expect(request.aba_units?.[0]?.unit_id).toBe("u1-cond_a1");

    const notes = draft.limitations.find((item) => item.code === "sessions_with_health_notes");
    expect(notes?.detail).toContain("u1-cond_a2");
    expect(notes?.detail).toContain("corrupt_manifest");
    expect(draft.limitations.map((item) => item.code)).not.toContain("unhealthy_sessions_excluded");
    expect(draft.limitations.map((item) => item.code)).not.toContain("ragged_condition_groups");

    expect(draft.planes.every((plane) => plane.available)).toBe(true);
    expect(draft.recipes).toHaveLength(1);
    expect(draft.provenance.experiment_id).toBe("exp.demo");
    expect(markdown).toContain("# Отчёт: Демо A/B/A");
    expect(markdown).toContain("## Ограничения");
  });

  it("unavailable metric values are excluded with a typed reason, not silently dropped", async () => {
    const client = clientStub(effectEnvelope(), {
      health: fullHealth(),
      failDetailFor: ["u2-cond_b"],
    });
    const store = new ReportsStore({ client: client as unknown as LntApiClient });
    const { draft } = await store.buildReport(abaDetail());

    const request = client.submitted[0];
    if (request === undefined || request.kind !== "aba")
      throw new Error("ожидается один aba-запрос");
    expect(request.aba_units).toHaveLength(1);
    const codes = draft.limitations.map((item) => item.code);
    expect(codes).toContain("unhealthy_sessions_excluded");
    const excluded = draft.limitations.find((item) => item.code === "unhealthy_sessions_excluded");
    expect(excluded?.detail).toContain("u2-cond_b");
    expect(excluded?.detail).toContain("value_unavailable");
  });

  it("refusal envelope maps to refusal outcome without causal boilerplate", async () => {
    const envelope = effectEnvelope();
    envelope.result_kind = "refusal";
    envelope.result = { reason_code: "a_drift_exceeds_half_effect_or_two_sd" };
    const client = clientStub(envelope, { health: fullHealth() });
    const store = new ReportsStore({ client: client as unknown as LntApiClient });
    const { draft } = await store.buildReport(abaDetail());
    expect(draft.outcome.kind).toBe("refusal");
    const refusal = draft.limitations.find((item) => item.code === "statistics_refusal");
    expect(refusal?.detail).toContain("a_drift_exceeds_half_effect_or_two_sd");
    expect(draft.limitations.map((item) => item.code)).not.toContain(
      "causal_inference_not_available",
    );
  });

  it("unavailable input reference becomes a typed plane limitation", async () => {
    const client = clientStub(effectEnvelope(), {
      health: fullHealth(),
      planeStatus: "manifest_schema_v1",
    });
    const store = new ReportsStore({ client: client as unknown as LntApiClient });
    const { draft } = await store.buildReport(abaDetail());
    expect(draft.planes.every((plane) => !plane.available)).toBe(true);
    const planes = draft.limitations.find((item) => item.code === "input_reference_unavailable");
    expect(planes?.detail).toContain("manifest_schema_v1");
  });

  it("recipes endpoint failure degrades to the honest unlinked limitation", async () => {
    const client = clientStub(effectEnvelope(), { health: fullHealth(), recipesFail: true });
    const store = new ReportsStore({ client: client as unknown as LntApiClient });
    const { draft } = await store.buildReport(abaDetail());
    expect(draft.recipes).toHaveLength(0);
    expect(draft.limitations.map((item) => item.code)).toContain("recipes_unlinked");
  });
});
