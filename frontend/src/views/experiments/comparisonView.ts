/** Панель сравнения (todo 43): проверка сравнимости → расчёт через durable
 * statistics-runs → результат с обязательной маркировкой. Гейт смешанных
 * типов блокирует расчёт с точной причиной; исключённые участники не
 * входят в пары; недостающие значения — явно с кодом причины. */

import type { LntApiClient } from "../../api/client";
import type {
  AbaUnitInput,
  ComparabilityReport,
  PairInput,
  StatisticsResultEnvelope,
} from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import type { ExperimentDetail } from "./experimentsStore";
import { currentState } from "./memberQc";
import type { MemberRow } from "./memberTableView";
import { renderResultPanel } from "./resultPanel";
import type { EffectView } from "./resultPanel";

const POLL_INTERVAL_MS = 300;
const POLL_LIMIT = 40;

function labeled(labelText: string, control: HTMLElement): HTMLElement {
  return el("label", { className: "lnt-field-inline field cmd-field" }, [
    el("span", { className: "lnt-label-text field-label cmd-label", text: labelText }),
    control,
  ]);
}

export interface ComparisonOptions {
  client: Pick<LntApiClient, "research" | "statistics">;
  /** Значение estimand по сессии; null — значение недоступно. */
  valueSource: (
    sessionId: string,
    featureKey: string,
    signal: AbortSignal,
  ) => Promise<number | null>;
}

export function effectFromPayload(raw: unknown): EffectView | null {
  if (typeof raw !== "object" || raw === null) return null;
  const record = raw as Record<string, unknown>;
  const mean = record.mean_effect;
  const median = record.median_effect;
  const robust = record.robust_effect;
  if (typeof mean !== "number" || typeof median !== "number" || typeof robust !== "number")
    return null;
  const interval = record.interval;
  const low =
    typeof interval === "object" &&
    interval !== null &&
    typeof (interval as Record<string, unknown>).low === "number"
      ? ((interval as Record<string, number>).low ?? null)
      : null;
  const high =
    typeof interval === "object" &&
    interval !== null &&
    typeof (interval as Record<string, unknown>).high === "number"
      ? ((interval as Record<string, number>).high ?? null)
      : null;
  return { mean, median, robust, intervalLow: low, intervalHigh: high };
}

export class ComparisonView {
  readonly root: HTMLElement;
  private readonly options: ComparisonOptions;
  private detail: ExperimentDetail | null = null;
  private rows: MemberRow[] = [];
  private lastReport: ComparabilityReport | null = null;
  private controller = new AbortController();
  private resultHost: HTMLElement;
  private readonly gateHost: HTMLElement;
  private readonly pairbarHost: HTMLElement;
  private readonly featureInput: HTMLInputElement;
  private readonly unitsInput: HTMLInputElement;
  private readonly seedInput: HTMLInputElement;

  constructor(options: ComparisonOptions) {
    this.options = options;
    this.featureInput = el("input", {
      className: "lnt-input ctl",
      attrs: { type: "text", id: "lnt-exp-feature", "aria-label": "Оцениваемый признак" },
    });
    this.unitsInput = el("input", {
      className: "lnt-input ctl",
      attrs: { type: "text", id: "lnt-exp-units", "aria-label": "Единицы измерения" },
    });
    this.unitsInput.value = "В²/Гц";
    this.seedInput = el("input", {
      className: "lnt-input ctl",
      attrs: { type: "number", id: "lnt-exp-seed", "aria-label": "Seed расчёта" },
    });
    this.seedInput.value = "43";
    const checkButton = el("button", {
      className: "lnt-btn btn-secondary",
      text: "Проверить сравнимость",
      attrs: { type: "button", id: "lnt-exp-check-comparability" },
    });
    checkButton.addEventListener("click", () => void this.runComparability());
    const runButton = el("button", {
      className: "lnt-btn lnt-btn-primary btn",
      text: "Рассчитать контраст",
      attrs: { type: "button", id: "lnt-exp-run-analysis" },
    });
    runButton.addEventListener(
      "click",
      () =>
        void this.runAnalysis(
          this.featureInput.value.trim(),
          this.unitsInput.value.trim() || "у.е.",
          Number(this.seedInput.value) || 0,
        ),
    );
    this.resultHost = el("div", {});
    this.gateHost = el("div", {
      className: "comparability-gate",
      attrs: { role: "status", "data-state": "unknown" },
      text: "Проверка сравнимости не выполнена — запустите проверку перед расчётом.",
    });
    this.pairbarHost = el("div", { className: "pairbar", attrs: { "aria-label": "Пара условий" } }, [
      el("div", { className: "pair-slot" }, [
        el("span", { className: "pair-role", text: "A" }),
        el("span", { className: "pair-name", text: "условие не выбрано" }),
      ]),
      el("div", { className: "pair-slot" }, [
        el("span", { className: "pair-role", text: "Б" }),
        el("span", { className: "pair-name", text: "условие не выбрано" }),
      ]),
      el("span", { className: "pair-delta", text: "Δ —" }),
    ]);
    const controls = el("div", { className: "lnt-exp-actions cmdbar" }, [
      el("div", { className: "cmd-fields" }, [
        labeled("Признак", this.featureInput),
        labeled("Единицы", this.unitsInput),
        labeled("Seed", this.seedInput),
      ]),
      el("div", { className: "cmd-actions" }, [checkButton, runButton]),
    ]);
    this.root = el("section", { className: "lnt-exp-comparison" }, [
      el("h2", { className: "placeholder-title panel-title", text: "Сравнение" }),
      el("p", {
        className: "lnt-helper-text",
        text: "Парные оценки с интервалами; для A/B/A — отдельная панель дрейфа A. Расчёт выполняется сервером (statistics-runs).",
      }),
      controls,
      this.gateHost,
      this.pairbarHost,
      this.resultHost,
    ]);
  }

  setContext(detail: ExperimentDetail, rows: MemberRow[]): void {
    this.detail = detail;
    this.rows = rows;
    if (this.featureInput.value === "") {
      this.featureInput.value = String(detail.experiment.primary_estimands?.[0]?.feature_key ?? "");
    }
    this.renderPairbar();
    this.renderIntro();
  }

  /** Полоса пары А—Б (для A/B/A — А1/Б/А2): только слоты условий и счётчики,
   * никакой числовой сводки — расчёт остаётся в resultHost. */
  private renderPairbar(): void {
    this.pairbarHost.replaceChildren();
    const labels = ["A", "Б", "A2"];
    for (const [index, conditionId] of this.orderedConditions().entries()) {
      const count = (this.includedByCondition().get(conditionId) ?? []).length;
      this.pairbarHost.append(
        el("div", { className: "pair-slot" }, [
          el("span", { className: "pair-role", text: labels[index] ?? `Слот ${String(index + 1)}` }),
          el("span", { className: "pair-name", text: conditionId }),
          el("span", { className: "pair-meta", text: `N=${String(count)}` }),
        ]),
      );
    }
    this.pairbarHost.append(el("span", { className: "pair-delta", text: "Δ —" }));
  }

  abort(): void {
    this.controller.abort();
  }

  private includedByCondition(): Map<string, MemberRow[]> {
    const map = new Map<string, MemberRow[]>();
    for (const row of this.rows) {
      if (currentState(row.inclusion) === "excluded") continue;
      const list = map.get(row.conditionId) ?? [];
      list.push(row);
      map.set(row.conditionId, list);
    }
    for (const list of map.values()) list.sort((a, b) => a.order - b.order);
    return map;
  }

  private renderIntro(): void {
    const protocolKind = String(this.detail?.experiment.protocol.kind ?? "");
    this.resultHost.replaceChildren(
      el("p", {
        className: "lnt-exp-meta-line",
        text: `План: ${protocolKind}. Проверьте сравнимость условий, затем запустите расчёт.`,
      }),
    );
  }

  /** Условия в порядке шагов протокола (не по алфавиту): для A/B/A критично. */
  private orderedConditions(): string[] {
    const steps = this.detail?.experiment.steps ?? [];
    return [...steps]
      .sort((a, b) => Number(a.order) - Number(b.order))
      .map((step) => String(step.condition_id));
  }

  /** Группы включённых участников в порядке протокола. */
  private groupedInProtocolOrder(): MemberRow[][] {
    const included = this.includedByCondition();
    return this.orderedConditions()
      .map((conditionId) => included.get(conditionId) ?? [])
      .filter((rows) => rows.length > 0);
  }

  async runComparability(): Promise<void> {
    if (!this.detail) return;
    this.controller.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const groups = this.groupedInProtocolOrder();
    if (groups.length < 2) {
      this.showBanner(
        "Для проверки сравнимости нужно минимум два условия с включёнными участниками.",
        "warn",
      );
      return;
    }
    const first = groups[0]?.[0];
    const second = groups[1]?.[0];
    if (!first || !second) {
      this.showBanner("В одном из условий нет доступных участников.", "warn");
      return;
    }
    try {
      const report = await this.options.client.research.comparabilityCheck(
        {
          left: { session_id: first.sessionId },
          right: { session_id: second.sessionId },
        },
        { signal },
      );
      this.lastReport = report;
      this.renderReport(report);
    } catch (error) {
      if (!signal.aborted)
        this.showBanner(`Проверка сравнимости не удалась: ${String(error)}`, "error");
    }
  }

  private renderReport(report: ComparabilityReport): void {
    const blocks = report.findings.filter((f) => f.level === "block");
    if (!report.comparable) {
      const reason = blocks.map((f) => f.code).join(", ");
      this.gateHost.setAttribute("data-state", "blocked");
      this.gateHost.textContent = `Сравнение заблокировано проверкой сравнимости. Точная причина: ${reason}. Числовой расчёт запрещён до устранения.`;
      this.resultHost.replaceChildren(
        el("div", { className: "lnt-exp-banner lnt-exp-banner-warn banner", attrs: { role: "alert" } }, [
          el("strong", { text: "Сравнение заблокировано проверкой сравнимости." }),
          el("p", { text: `Точная причина: ${reason}. Числовой расчёт запрещён до устранения.` }),
          ...report.findings.map((f) =>
            el("p", {
              className: "lnt-exp-meta-line",
              text: `${f.dimension}: ${String(f.level)} · ${String(f.code)} · поля: ${Array.isArray(f.fields) ? (f.fields as string[]).join(", ") : String(f.fields)}`,
            }),
          ),
        ]),
      );
      announcePolite("Сравнение заблокировано проверкой сравнимости");
      return;
    }
    this.gateHost.setAttribute("data-state", "ok");
    this.gateHost.textContent = `Сравнимость подтверждена (${String(report.findings.length)} измерений без блокировок). Можно запускать расчёт.`;
    this.showBanner(
      `Сравнимость подтверждена (${String(report.findings.length)} измерений без блокировок). Можно запускать расчёт.`,
      "ok",
    );
  }

  async runAnalysis(featureKey: string, units: string, seed: number): Promise<void> {
    if (!this.detail) return;
    if (this.lastReport !== null && !this.lastReport.comparable) {
      this.showBanner("Расчёт заблокирован: сравнимость не подтверждена.", "warn");
      return;
    }
    this.controller.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const kind = String(this.detail.experiment.protocol.kind);
    try {
      const request =
        kind === "aba"
          ? await this.buildAbaRequest(featureKey, units, seed, signal)
          : await this.buildPairsRequest(
              kind as "ab" | "repeated_blocks" | "cohort" | "longitudinal",
              featureKey,
              units,
              seed,
              signal,
            );
      const snapshot = await this.options.client.statistics.submit(
        this.detail.experiment.experiment_id,
        request,
      );
      const envelope = await this.pollResult(snapshot.job_id, signal);
      this.renderEnvelope(envelope);
      announcePolite("Результат сравнения получен");
    } catch (error) {
      if (!signal.aborted)
        this.showBanner(
          `Расчёт не выполнен: ${error instanceof Error ? error.message : String(error)}`,
          "error",
        );
    }
  }

  private async pollResult(jobId: string, signal: AbortSignal): Promise<StatisticsResultEnvelope> {
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      const payload = await this.options.client.statistics.result(jobId, { signal });
      if ("result_kind" in payload) return payload as StatisticsResultEnvelope;
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
    throw new Error("превышено время ожидания результата статистики");
  }

  private async buildPairsRequest(
    kind: "ab" | "repeated_blocks" | "cohort" | "longitudinal",
    featureKey: string,
    units: string,
    seed: number,
    signal: AbortSignal,
  ): Promise<{
    kind: typeof kind;
    estimand: string;
    units: string;
    pairs: PairInput[];
    aba_units?: AbaUnitInput[];
    seed: number;
  }> {
    const groups = this.groupedInProtocolOrder();
    const left = groups[0] ?? [];
    const right = groups[1] ?? [];
    const pairs: PairInput[] = [];
    let missing = 0;
    const count = Math.min(left.length, right.length);
    for (let i = 0; i < count; i += 1) {
      const a = left[i];
      const b = right[i];
      if (!a || !b) continue;
      const [valueA, valueB] = await Promise.all([
        this.options.valueSource(a.sessionId, featureKey, signal),
        this.options.valueSource(b.sessionId, featureKey, signal),
      ]);
      if (valueA === null || valueB === null) {
        missing += 1;
        continue;
      }
      pairs.push({ unit_id: `${a.sessionId}~${b.sessionId}`, value_a: valueA, value_b: valueB });
    }
    if (missing > 0) {
      this.showBanner(
        `${String(missing)} пар(ы) пропущены: значения признака недоступны (причина: нет данных метрик).`,
        "warn",
      );
    }
    return { kind, estimand: featureKey, units, pairs, seed };
  }

  private async buildAbaRequest(
    featureKey: string,
    units: string,
    seed: number,
    signal: AbortSignal,
  ): Promise<{
    kind: "aba";
    estimand: string;
    units: string;
    aba_units: AbaUnitInput[];
    seed: number;
  }> {
    const [g1, g2, g3] = this.groupedInProtocolOrder();
    const abaUnits: AbaUnitInput[] = [];
    const count = Math.min(g1?.length ?? 0, g2?.length ?? 0, g3?.length ?? 0);
    for (let i = 0; i < count; i += 1) {
      const s1 = g1?.[i];
      const s2 = g2?.[i];
      const s3 = g3?.[i];
      if (!s1 || !s2 || !s3) continue;
      const [a1, b, a2] = await Promise.all([
        this.options.valueSource(s1.sessionId, featureKey, signal),
        this.options.valueSource(s2.sessionId, featureKey, signal),
        this.options.valueSource(s3.sessionId, featureKey, signal),
      ]);
      if (a1 === null || b === null || a2 === null) continue;
      abaUnits.push({ unit_id: s1.sessionId, value_a1: a1, value_b: b, value_a2: a2 });
    }
    return { kind: "aba", estimand: featureKey, units, aba_units: abaUnits, seed };
  }

  private renderEnvelope(envelope: StatisticsResultEnvelope): void {
    const meta = envelope.metadata;
    if (envelope.result_kind === "refusal") {
      const reason = String((envelope.result as Record<string, unknown>).reason_code ?? "unknown");
      this.resultHost.replaceChildren(
        renderResultPanel({
          title: "Результат сравнения",
          effect: null,
          refusalReason: reason,
          metadata: meta,
        }),
      );
      return;
    }
    if (envelope.result_kind === "effect") {
      const effectRaw = (envelope.result as Record<string, unknown>).effect;
      const driftRaw = (envelope.result as Record<string, unknown>).drift;
      this.resultHost.replaceChildren(
        renderResultPanel({
          title: "Результат сравнения",
          effect: effectFromPayload(effectRaw),
          drift: driftRaw ? effectFromPayload(driftRaw) : null,
          metadata: meta,
          limitationsExtra:
            meta.estimator === "qualified_within_run_contrast"
              ? ["Квалифицированный внутрисерийный контраст: причинный вывод недоступен."]
              : [],
        }),
      );
      return;
    }
    this.resultHost.replaceChildren(
      renderResultPanel({
        title: "Описательный результат (без интервала)",
        effect: effectFromPayload(envelope.result),
        metadata: meta,
        limitationsExtra: ["N ниже минимума инференции: интервал не строится."],
      }),
    );
  }

  private showBanner(message: string, tone: "ok" | "warn" | "error"): void {
    const existing = this.root.querySelector(".lnt-exp-compare-status");
    existing?.remove();
    const banner = el("p", {
      className: `lnt-exp-banner lnt-exp-banner-${tone} lnt-exp-compare-status banner banner-inline`,
      attrs: tone === "error" ? { role: "alert" } : { role: "status" },
      text: message,
    });
    this.resultHost.before(banner);
  }
}
