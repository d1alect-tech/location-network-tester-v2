/** Эксперименты/гипотезы/статистика/тренды единого мок-бэкенда (только e2e/spec).
 * Повторяет контракты routes_experiments.py / routes_statistics.py /
 * routes_research.py / routes_quality.py. Числа — только canned-золото из
 * mockGolden (семантика aba.py в TS не дублируется). */

import { type AbaUnit, type StatisticsRequest, buildStatisticsEnvelope } from "./mockGolden";
import { type MockHttpReply, type MockHttpRequest, failure, notFound, ok } from "./mockHttp";
import { requireNonce } from "./mockJobStore";

function mean(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export class ResearchStore {
  readonly experiments = new Map<string, Record<string, unknown>>();
  readonly hypotheses = new Map<string, Record<string, unknown>>();
  readonly statJobs = new Map<string, Record<string, unknown>>();
  /** Следующая мутация гипотезы вернёт 409 (конкурентная правка). */
  conflictNextHypothesis = false;
  /** Пара сессий, для которой сравнимость блокируется смешанным типом. */
  mixedTypeSessions = new Set<string>();
  private jobCounter = 0;

  detail(experimentId: string): Record<string, unknown> | null {
    return this.experiments.get(experimentId) ?? null;
  }

  nextJobId(): string {
    this.jobCounter += 1;
    return `job-${String(this.jobCounter)}`;
  }
}

function comparability(
  store: ResearchStore,
  body: {
    left?: { session_id?: string };
    right?: { session_id?: string };
  },
): MockHttpReply {
  const left = body.left?.session_id ?? "";
  const right = body.right?.session_id ?? "";
  if (store.mixedTypeSessions.has(left) || store.mixedTypeSessions.has(right)) {
    return ok({
      comparable: false,
      findings: [
        {
          dimension: "comparison_kind",
          level: "block",
          code: "comparison_kind_mismatch",
          fields: ["session_type"],
        },
      ],
    });
  }
  return ok({
    comparable: true,
    findings: [{ dimension: "quality", level: "ok", code: "quality_ok", fields: [] }],
  });
}

function experiments(store: ResearchStore, request: MockHttpRequest): MockHttpReply | null {
  const { method, path } = request;
  if (path === "/api/v2/experiments" && method === "GET") {
    return ok({ items: [...store.experiments.values()], next_cursor: null });
  }
  if (path === "/api/v2/experiments" && method === "POST") {
    const nonce = requireNonce(request);
    if (nonce) return nonce;
    const body = request.bodyJson<{ experiment?: Record<string, unknown> }>();
    const experiment = body.experiment;
    if (!experiment || typeof experiment.experiment_id !== "string") {
      return failure(422, { code: "experiment_schema_invalid", detail: "нет experiment_id" });
    }
    store.experiments.set(experiment.experiment_id, experiment);
    return { status: 201, body: experiment };
  }
  const expMatch = /^\/api\/v2\/experiments\/([^/]+)(\/.*)?$/.exec(path);
  if (!expMatch) return null;
  const id = decodeURIComponent(expMatch[1] ?? "");
  const suffix = expMatch[2] ?? "";
  if (method === "GET" && suffix === "") {
    const record = store.detail(id);
    return record ? ok(record) : notFound("эксперимент не найден");
  }
  if (method === "PUT" && suffix === "") {
    const nonce = requireNonce(request);
    if (nonce) return nonce;
    const record = store.detail(id);
    if (!record) return notFound("эксперимент не найден");
    const body = request.bodyJson<{
      expected_revision?: number;
      experiment?: Record<string, unknown>;
    }>();
    if (Number(body.expected_revision) !== Number(record.revision)) {
      return failure(409, {
        detail: {
          code: "experiment_revision_conflict",
          detail: `конфликт revision: ожидалась ${String(body.expected_revision)}, текущая ${String(record.revision)}`,
        },
      });
    }
    const updated = { ...body.experiment, revision: Number(record.revision) + 1 };
    store.experiments.set(id, updated);
    return ok(updated);
  }
  if (method === "GET" && (suffix === "/members" || suffix === "/steps")) {
    const record = store.detail(id);
    if (!record) return notFound("эксперимент не найден");
    const key = suffix === "/members" ? "members" : "steps";
    return ok({ items: record[key] ?? [], next_cursor: null });
  }
  if (method === "POST" && suffix === "/statistics-runs") {
    const nonce = requireNonce(request);
    if (nonce) return nonce;
    const jobId = store.nextJobId();
    const body = request.bodyJson<StatisticsRequest & { aba_units?: AbaUnit[] }>();
    const revision = Number(store.detail(id)?.revision ?? 1);
    store.statJobs.set(jobId, buildStatisticsEnvelope(id, body, revision, jobId));
    return {
      status: 202,
      body: {
        schema_version: 1,
        version: 1,
        job_id: jobId,
        kind: "research_analysis",
        status: "queued",
        stage: "queued",
        series_index: null,
        series_total: null,
        written_sessions: [],
        result: null,
        error_code: null,
        error_message: null,
      },
    };
  }
  return null;
}

function hypotheses(store: ResearchStore, request: MockHttpRequest): MockHttpReply | null {
  const { method, path } = request;
  if (path === "/api/v2/hypotheses" && method === "POST") {
    const nonce = requireNonce(request);
    if (nonce) return nonce;
    const body = request.bodyJson<{ hypothesis?: Record<string, unknown> }>();
    const hypothesis = body.hypothesis;
    if (!hypothesis || typeof hypothesis.hypothesis_id !== "string") {
      return failure(422, { code: "hypothesis_schema_invalid", detail: "нет hypothesis_id" });
    }
    store.hypotheses.set(hypothesis.hypothesis_id, { ...hypothesis, status_label: "черновик" });
    return { status: 201, body: store.hypotheses.get(hypothesis.hypothesis_id) };
  }
  if (path === "/api/v2/hypotheses" && method === "GET") {
    return ok({ items: [...store.hypotheses.values()], next_cursor: null });
  }
  const hypMatch = /^\/api\/v2\/hypotheses\/([^/]+)(\/.*)?$/.exec(path);
  if (!hypMatch) return null;
  const id = decodeURIComponent(hypMatch[1] ?? "");
  if (method === "GET" && (hypMatch[2] === "" || hypMatch[2] === undefined)) {
    const record = store.hypotheses.get(id);
    return record ? ok(record) : notFound("гипотеза не найдена");
  }
  if (method === "PUT") {
    const nonce = requireNonce(request);
    if (nonce) return nonce;
    const record = store.hypotheses.get(id);
    if (!record) return notFound("гипотеза не найдена");
    const body = request.bodyJson<{
      expected_revision?: number;
      hypothesis?: Record<string, unknown>;
    }>();
    if (
      store.conflictNextHypothesis ||
      Number(body.expected_revision) !== Number(record.revision)
    ) {
      store.conflictNextHypothesis = false;
      return failure(409, {
        detail: {
          code: "hypothesis_revision_conflict",
          detail: "конфликт revision гипотезы: запись изменена другим процессом",
        },
      });
    }
    const updated = {
      ...body.hypothesis,
      revision: Number(record.revision) + 1,
      status_label: String(body.hypothesis?.status ?? ""),
    };
    store.hypotheses.set(id, updated);
    return ok(updated);
  }
  return null;
}

function trends(request: MockHttpRequest): MockHttpReply | null {
  if (request.path !== "/api/v2/trends/query" || request.method !== "POST") return null;
  const nonce = requireNonce(request);
  if (nonce) return nonce;
  const body = request.bodyJson<{
    observations?: { condition: string; outcome: number | null }[];
    units?: string;
  }>();
  const observations = body.observations ?? [];
  const byCondition = new Map<string, number[]>();
  let usable = 0;
  for (const observation of observations) {
    if (typeof observation.outcome !== "number") continue;
    usable += 1;
    const list = byCondition.get(observation.condition) ?? [];
    list.push(observation.outcome);
    byCondition.set(observation.condition, list);
  }
  return ok({
    trends: [...byCondition.entries()].map(([groupValue, values]) => ({
      group_dimension: "condition",
      group_value: groupValue,
      n: values.length,
      missing_count: 0,
      mean: mean(values),
      result_kind: "descriptive_exploratory",
      exploratory: true,
    })),
    correlations: [],
    data_quality: {
      input_count: observations.length,
      usable_count: usable,
      missing_timestamp_count: observations.length - usable,
      duplicate_count: 0,
      dedupe_policy: "keep_first",
      gaps: [],
    },
    normalized_timestamps: [],
    result_kind: "descriptive_exploratory",
    metadata: {
      units: String(body.units ?? "у.е."),
      estimator: "descriptive_longitudinal",
      n: usable,
      provenance: { seed: 0, dedupe_policy: "keep_first" },
    },
  });
}

/** Маршруты v2-исследователя; null — не наш путь. */
export function handleResearch(
  store: ResearchStore,
  request: MockHttpRequest,
): MockHttpReply | null {
  if (request.path === "/api/v2/comparability/check" && request.method === "POST") {
    return comparability(store, request.bodyJson());
  }
  const jobsResultMatch = /^\/api\/v2\/statistics-runs\/([^/]+)\/result$/.exec(request.path);
  if (jobsResultMatch && request.method === "GET") {
    const envelope = store.statJobs.get(decodeURIComponent(jobsResultMatch[1] ?? ""));
    return envelope ? ok(envelope) : notFound("статистическая задача не найдена");
  }
  return experiments(store, request) ?? hypotheses(store, request) ?? trends(request);
}
