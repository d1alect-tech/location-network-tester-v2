/** ТЕСТОВЫЙ исследовательский бэкенд v2 (только e2e/spec): повторяет
 * контракты routes_experiments.py / routes_statistics.py / routes_research.py
 * / routes_quality.py. Золотые числа интервалов получены репликацией numpy
 * семантики estimate_paired/analyze_aba (seeded_block_bootstrap, 10000×N,
 * квантили 2.5/97.5) — вывод задокументирован в DoneClaim risks. */

import type { Page, Route } from "@playwright/test";

const NONCE = "test-nonce-t43";

export interface FixtureSession {
  id: string;
  label: string | null;
  health: string;
  session_type: string;
  /** Значение feature band_mid_total для valueSource. */
  metric: number;
}

export const ABA_FIXTURE: Record<string, { a1: number; b: number; a2: number }> = {
  "unit-1": { a1: 10.0, b: 12.0, a2: 10.2 },
  "unit-2": { a1: 11.0, b: 13.5, a2: 11.1 },
  "unit-3": { a1: 9.5, b: 11.0, a2: 9.6 },
  "unit-4": { a1: 10.5, b: 12.5, a2: 10.4 },
};

/** Синтетический набор с дрейфом A (a2 = a1 + 3) → гарантированный refusal. */
export const DRIFT_FIXTURE: Record<string, { a1: number; b: number; a2: number }> = {
  "unit-1": { a1: 10.0, b: 14.0, a2: 13.0 },
  "unit-2": { a1: 11.0, b: 15.5, a2: 14.0 },
  "unit-3": { a1: 9.5, b: 12.5, a2: 12.5 },
  "unit-4": { a1: 10.5, b: 13.5, a2: 13.5 },
};

function sessionsOf(
  fixture: Record<string, { a1: number; b: number; a2: number }>,
  prefix: string,
): FixtureSession[] {
  const rows: FixtureSession[] = [];
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
  return rows;
}

/** Канонические золотые интервалы (numpy-репликация бэкенда). */
const GOLDEN_DEMO_INTERVAL = [1.5999999999999996, 2.3124999999999996] as const;
const GOLDEN_DRIFT_INTERVAL = [-0.04999999999999982, 0.17499999999999938] as const;

interface AbaUnitPayload {
  unit_id: string;
  value_a1: number;
  value_b: number;
  value_a2: number;
}

function mean(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? (sorted[mid] as number)
    : ((sorted[mid - 1] as number) + (sorted[mid] as number)) / 2;
}

function trimmedMean(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const trim = Math.floor(sorted.length * 0.2);
  return trim > 0 ? mean(sorted.slice(trim, sorted.length - trim)) : mean(sorted);
}

function sd(values: number[]): number {
  if (values.length < 2) return 0;
  const m = mean(values);
  return Math.sqrt(mean(values.map((v) => (v - m) ** 2)));
}

export class MockResearchBackend {
  readonly sessions: FixtureSession[];
  readonly experiments = new Map<string, Record<string, unknown>>();
  readonly hypotheses = new Map<string, Record<string, unknown>>();
  readonly jobs = new Map<string, Record<string, unknown>>();
  /** Следующая мутация гипотезы вернёт 409 (конкурентная правка). */
  conflictNextHypothesis = false;
  /** Пара сессий, для которой сравнимость блокируется смешанным типом. */
  mixedTypeSessions = new Set<string>();
  /** Todo 44: типизированное состояние устройства для панели диагностики
   * (device_absent — штатное состояние, а не ошибка). */
  deviceState = "ready";
  requestLog: { method: string; path: string }[] = [];
  private jobCounter = 0;

  constructor() {
    this.sessions = [
      ...sessionsOf(ABA_FIXTURE, "aba"),
      ...sessionsOf(DRIFT_FIXTURE, "drift"),
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
    ];
    // Демо-эксперимент уже существует: полный путь create→view покрыт мастером.
  }

  configPayload(): Record<string, unknown> {
    return {
      root: "C:\\lnt-sessions-test",
      profiles: [],
      defaults: {
        simulate: {
          duration_s: 2.4,
          sample_rate_hz: 20_000_000,
          seed: 1,
          repeat: 3,
          interval_s: 5,
        },
        capture: {
          duration_s: 2.4,
          sample_rate_hz: 20_000_000,
          range_v: 5,
          repeat: 3,
          interval_s: 5,
        },
        ranges: [0.5, 1, 5],
      },
      build_id: "t43-build",
      mutation_nonce: NONCE,
      static_asset_hash: "test",
      static_assets: {},
    };
  }

  private detail(experimentId: string): Record<string, unknown> | null {
    return this.experiments.get(experimentId) ?? null;
  }

  private statisticsEnvelope(
    experimentId: string,
    body: Record<string, unknown>,
  ): Record<string, unknown> {
    const units = String(body.units ?? "у.е.");
    const meta = {
      units,
      sampling_unit: "measurement_session",
      hierarchy: ["site", "unit"],
      n: 0,
      missing_count: 0,
      exclusions: [] as unknown[],
      estimator: "",
      interval_method: "",
      provenance: {
        experiment_id: experimentId,
        experiment_revision: this.detail(experimentId)?.revision ?? 1,
        estimand: String(body.estimand ?? ""),
        job_id: `job-${this.jobCounter}`,
      },
    };
    const abaUnits = (body.aba_units ?? []) as AbaUnitPayload[];
    if (body.kind !== "aba") {
      return {
        result_kind: "descriptive",
        result: {},
        metadata: { ...meta, n: 0, estimator: "unsupported_in_mock", interval_method: "none" },
      };
    }
    const contrastDiffs = abaUnits.map((u) => u.value_b - (u.value_a1 + u.value_a2) / 2);
    const driftDiffs = abaUnits.map((u) => u.value_a2 - u.value_a1);
    const driftMean = mean(driftDiffs);
    const contrastMean = mean(contrastDiffs);
    // Семантика aba.py: порог = max(0.5·|эффект|, 2·sd контрастных дельт).
    const threshold = Math.max(0.5 * Math.abs(contrastMean), 2 * sd(contrastDiffs));
    if (Math.abs(driftMean) > threshold) {
      return {
        result_kind: "refusal",
        result: {
          reason_code: "a_drift_exceeds_half_effect_or_two_sd",
          drift_effect: driftMean,
          contrast_effect: contrastMean,
        },
        metadata: {
          ...meta,
          n: abaUnits.length,
          estimator: "qualified_within_run_contrast",
          interval_method: "blocked_by_a_drift",
        },
      };
    }
    const canonical =
      experimentId === "exp.aba.demo" &&
      JSON.stringify(contrastDiffs.map((d) => Math.round(d * 8))) ===
        JSON.stringify([15, 20, 12, 16]);
    const effectInterval = canonical ? [...GOLDEN_DEMO_INTERVAL] : null;
    if (effectInterval === null) {
      // Вне канонического фикстурного набора интервал не выдумываем:
      // честный описательный результат без интервала (семантика бэкенда
      // DescriptiveEffect / interval_method none_insufficient_n).
      return {
        result_kind: "descriptive",
        result: {
          mean_effect: contrastMean,
          median_effect: median(contrastDiffs),
          robust_effect: trimmedMean(contrastDiffs),
          interval: null,
          stored_differences: contrastDiffs,
        },
        metadata: {
          ...meta,
          n: abaUnits.length,
          estimator: "qualified_within_run_contrast",
          interval_method: "none_insufficient_n",
        },
      };
    }
    return {
      result_kind: "effect",
      result: {
        effect: {
          mean_effect: contrastMean,
          median_effect: median(contrastDiffs),
          robust_effect: trimmedMean(contrastDiffs),
          interval: { low: effectInterval[0], high: effectInterval[1], confidence_level: 0.95 },
          stored_differences: contrastDiffs,
        },
        drift: {
          mean_effect: driftMean,
          median_effect: median(driftDiffs),
          robust_effect: trimmedMean(driftDiffs),
          interval: {
            low: GOLDEN_DRIFT_INTERVAL[0],
            high: GOLDEN_DRIFT_INTERVAL[1],
            confidence_level: 0.95,
          },
          stored_differences: driftDiffs,
        },
        description_ru: "Квалифицированный внутрисерийный контраст; причинный вывод недоступен.",
      },
      metadata: {
        ...meta,
        n: abaUnits.length,
        estimator: "qualified_within_run_contrast",
        interval_method: "seeded_block_bootstrap_percentile_95",
      },
    };
  }

  async handle(route: Route): Promise<void> {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/static\/v2/, "");
    const method = route.request().method();
    this.requestLog.push({ method, path });
    const json = (status: number, body?: unknown): Promise<void> =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: body === undefined ? "" : JSON.stringify(body),
      });
    const nonceOk = route.request().headers()["x-lnt-mutation-nonce"] === NONCE;

    if (path === "/api/config" && method === "GET") return json(200, this.configPayload());
    if (path === "/api/health" && method === "GET") {
      return json(200, { status: "ok", build_id: "t43-build" });
    }
    if (path === "/api/jobs" && method === "GET") return json(200, { items: [] });
    if (path === "/api/catalog/sessions" && method === "GET") {
      return json(200, { items: this.sessions, next_cursor: null });
    }

    const spectrumMatch = /^\/api\/sessions\/([^/]+)\/spectrum$/.exec(path);
    if (spectrumMatch && method === "GET") {
      const points = Array.from({ length: 32 }, (_, i) => 1000 * 2 ** (i / 4));
      return json(200, {
        frequency_hz: points,
        psd_v2_per_hz: points.map((f) => 1e-8 / (f / 1000)),
        point_count: points.length,
      });
    }
    const sessionDetailMatch = /^\/api\/sessions\/([^/]+)$/.exec(path);
    if (sessionDetailMatch && method === "GET") {
      const session = this.sessions.find(
        (item) => item.id === decodeURIComponent(sessionDetailMatch[1] ?? ""),
      );
      if (!session) return json(404, { detail: "сессия не найдена" });
      return json(200, {
        name: session.id,
        manifest: {},
        analysis: {
          metrics: { band_mid_total: session.metric },
          ch1_input_reference:
            session.health === "ok"
              ? { status: "available", model_kind: "rc_shunt_v1" }
              : { status: "unavailable", reason_code: "analysis_unavailable" },
        },
        spectrum_available: true,
        waveform_available: false,
        ch2_available: false,
      });
    }

    // ===== BEGIN Todo 44: диагностика устройства, preflight, рецепты =====
    if (path === "/api/device/state" && method === "GET") {
      const descriptions: Record<string, [string, string]> = {
        ready: ["Устройство готово к захвату.", "Можно запускать измерения."],
        device_absent: [
          "Устройство не обнаружено на шине USB.",
          "Подключите осциллограф и проверьте кабель; драйвер WinUSB ставится через Zadig (VID 04B4/04B5).",
        ],
      };
      const entry = descriptions[this.deviceState] ?? descriptions.device_absent!;
      return json(200, {
        state: this.deviceState,
        description_ru: entry[0],
        recovery_action_ru: entry[1],
      });
    }
    if (path === "/api/capture/preflight" && method === "POST") {
      const findings: Record<string, unknown>[] = [];
      if (this.deviceState !== "ready") {
        findings.push({
          severity: "block",
          code: "device_not_ready",
          message_ru: "Устройство не готово к записи.",
          recovery_action_ru: "Выполните действие из диагностики устройства.",
        });
      }
      findings.push({
        severity: "warn",
        code: "baseline_not_requested",
        message_ru: "Самошум-базовая сессия не выбрана: приведение ко входу будет недоступно.",
        recovery_action_ru: "При необходимости снимите базовую сессию самошума в локации.",
      });
      return json(200, {
        ready: this.deviceState === "ready",
        device_state: this.deviceState,
        findings,
      });
    }
    if (path === "/api/analysis/recipes" && method === "GET") {
      return json(200, {
        items: [
          {
            recipe_id: "rec-default-spectrum",
            name: "Базовый спектр",
            sha256: "c".repeat(64),
            recipe: { window: "welch", bands: 512 },
          },
        ],
      });
    }
    if (path === "/api/profiles" && method === "GET") {
      return json(200, { items: [] });
    }
    // ===== END Todo 44 =====

    if (path === "/api/v2/comparability/check" && method === "POST") {
      const body = route.request().postDataJSON() as {
        left?: { session_id?: string };
        right?: { session_id?: string };
      };
      const left = body.left?.session_id ?? "";
      const right = body.right?.session_id ?? "";
      if (this.mixedTypeSessions.has(left) || this.mixedTypeSessions.has(right)) {
        return json(200, {
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
      return json(200, {
        comparable: true,
        findings: [{ dimension: "quality", level: "ok", code: "quality_ok", fields: [] }],
      });
    }

    if (path === "/api/v2/experiments" && method === "GET") {
      return json(200, { items: [...this.experiments.values()], next_cursor: null });
    }
    if (path === "/api/v2/experiments" && method === "POST") {
      if (!nonceOk) return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
      const body = route.request().postDataJSON() as { experiment?: Record<string, unknown> };
      const experiment = body.experiment;
      if (!experiment || typeof experiment.experiment_id !== "string") {
        return json(422, { code: "experiment_schema_invalid", detail: "нет experiment_id" });
      }
      this.experiments.set(experiment.experiment_id, experiment);
      return json(201, experiment);
    }
    const expMatch = /^\/api\/v2\/experiments\/([^/]+)(\/.*)?$/.exec(path);
    if (expMatch) {
      const id = decodeURIComponent(expMatch[1] ?? "");
      const suffix = expMatch[2] ?? "";
      if (method === "GET" && suffix === "") {
        const record = this.detail(id);
        return record ? json(200, record) : json(404, { detail: "эксперимент не найден" });
      }
      if (method === "PUT" && suffix === "") {
        if (!nonceOk) return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
        const record = this.detail(id);
        if (!record) return json(404, { detail: "эксперимент не найден" });
        const body = route.request().postDataJSON() as {
          expected_revision?: number;
          experiment?: Record<string, unknown>;
        };
        if (Number(body.expected_revision) !== Number(record.revision)) {
          return json(409, {
            detail: {
              code: "experiment_revision_conflict",
              detail: `конфликт revision: ожидалась ${String(body.expected_revision)}, текущая ${String(record.revision)}`,
            },
          });
        }
        const updated = { ...body.experiment, revision: Number(record.revision) + 1 };
        this.experiments.set(id, updated);
        return json(200, updated);
      }
      if (method === "GET" && (suffix === "/members" || suffix === "/steps")) {
        const record = this.detail(id);
        if (!record) return json(404, { detail: "эксперимент не найден" });
        const key = suffix === "/members" ? "members" : "steps";
        return json(200, { items: record[key] ?? [], next_cursor: null });
      }
      if (method === "POST" && suffix === "/statistics-runs") {
        if (!nonceOk) return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
        this.jobCounter += 1;
        const jobId = `job-${String(this.jobCounter)}`;
        const body = route.request().postDataJSON() as Record<string, unknown>;
        this.jobs.set(jobId, this.statisticsEnvelope(id, body));
        return json(202, {
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
        });
      }
    }
    const jobResultMatch = /^\/api\/v2\/statistics-runs\/([^/]+)\/result$/.exec(path);
    if (jobResultMatch && method === "GET") {
      const envelope = this.jobs.get(decodeURIComponent(jobResultMatch[1] ?? ""));
      return envelope
        ? json(200, envelope)
        : json(404, { detail: "статистическая задача не найдена" });
    }

    if (path === "/api/v2/hypotheses" && method === "POST") {
      if (!nonceOk) return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
      const body = route.request().postDataJSON() as { hypothesis?: Record<string, unknown> };
      const hypothesis = body.hypothesis;
      if (!hypothesis || typeof hypothesis.hypothesis_id !== "string") {
        return json(422, { code: "hypothesis_schema_invalid", detail: "нет hypothesis_id" });
      }
      this.hypotheses.set(hypothesis.hypothesis_id, { ...hypothesis, status_label: "черновик" });
      return json(201, this.hypotheses.get(hypothesis.hypothesis_id));
    }
    const hypMatch = /^\/api\/v2\/hypotheses\/([^/]+)(\/.*)?$/.exec(path);
    if (hypMatch) {
      const id = decodeURIComponent(hypMatch[1] ?? "");
      if (path === "/api/v2/hypotheses" || (hypMatch[2] === "" && method === "GET")) {
        const record = this.hypotheses.get(id);
        return record ? json(200, record) : json(404, { detail: "гипотеза не найдена" });
      }
      if (method === "PUT") {
        if (!nonceOk) return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
        const record = this.hypotheses.get(id);
        if (!record) return json(404, { detail: "гипотеза не найдена" });
        const body = route.request().postDataJSON() as {
          expected_revision?: number;
          hypothesis?: Record<string, unknown>;
        };
        if (
          this.conflictNextHypothesis ||
          Number(body.expected_revision) !== Number(record.revision)
        ) {
          this.conflictNextHypothesis = false;
          return json(409, {
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
        this.hypotheses.set(id, updated);
        return json(200, updated);
      }
    }
    if (path === "/api/v2/hypotheses" && method === "GET") {
      return json(200, { items: [...this.hypotheses.values()], next_cursor: null });
    }
    if (path === "/api/v2/trends/query" && method === "POST") {
      if (!nonceOk) return json(403, { code: "mutation_nonce_invalid", detail: "нет nonce" });
      const body = route.request().postDataJSON() as {
        observations?: { condition: string; outcome: number | null }[];
        units?: string;
      };
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
      return json(200, {
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

    return json(404, { detail: `нет мока: ${method} ${path}` });
  }
}

export async function attachResearchBackend(
  page: Page,
  backend: MockResearchBackend,
): Promise<void> {
  await page.route(
    (url) => url.pathname.startsWith("/api/") || url.pathname.includes("!/api/"),
    (route) => void backend.handle(route),
  );
}
