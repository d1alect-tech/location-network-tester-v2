/** Панель сравнения (todo 43): проверка сравнимости → расчёт через durable
 * statistics-runs → результат с обязательной маркировкой. Гейт смешанных
 * типов блокирует расчёт с точной причиной; исключённые участники не
 * входят в пары; недостающие значения — явно с кодом причины.
 * T11: группировка — в comparisonGroups, сборка запросов/опрос/отрисовка
 * исходов — в comparisonRunner; здесь каркас, состояние и оркестрация. */

import type { LntApiClient } from "../../api/client";
import type { ComparabilityReport } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { groupsInProtocolOrder, renderPairbarSlots } from "./comparisonGroups";
import {
  buildAbaPayload,
  buildPairsPayload,
  effectFromPayload as effectFromRunnerPayload,
  pollStatisticsResult,
  renderComparabilityOutcome,
  renderComparisonEnvelope,
} from "./comparisonRunner";
import type { ExperimentDetail } from "./experimentsStore";
import type { MemberRow } from "./memberTableView";
import type { EffectView } from "./resultPanel";

/** Реэкспорт для существующих импортов (driftDisplay.test.ts). */
export { effectFromRunnerPayload as effectFromPayload };
export type { EffectView };

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
    this.pairbarHost = el(
      "div",
      { className: "pairbar", attrs: { "aria-label": "Пара условий" } },
      [
        el("div", { className: "pair-slot" }, [
          el("span", { className: "pair-role", text: "A" }),
          el("span", { className: "pair-name", text: "условие не выбрано" }),
        ]),
        el("div", { className: "pair-slot" }, [
          el("span", { className: "pair-role", text: "Б" }),
          el("span", { className: "pair-name", text: "условие не выбрано" }),
        ]),
        el("span", { className: "pair-delta", text: "Δ —" }),
      ],
    );
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
    renderPairbarSlots(this.pairbarHost, this.rows, this.detail);
    this.renderIntro();
  }

  abort(): void {
    this.controller.abort();
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

  async runComparability(): Promise<void> {
    if (!this.detail) return;
    this.controller.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const groups = groupsInProtocolOrder(this.rows, this.detail);
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
      renderComparabilityOutcome(this.gateHost, this.resultHost, report, (message) =>
        this.showBanner(message, "ok"),
      );
    } catch (error) {
      if (!signal.aborted)
        this.showBanner(`Проверка сравнимости не удалась: ${String(error)}`, "error");
    }
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
    const groups = groupsInProtocolOrder(this.rows, this.detail);
    const { valueSource } = this.options;
    try {
      const request =
        kind === "aba"
          ? await buildAbaPayload(valueSource, groups, featureKey, units, seed, signal)
          : await buildPairsPayload(
              valueSource,
              groups,
              kind as "ab" | "repeated_blocks" | "cohort" | "longitudinal",
              featureKey,
              units,
              seed,
              signal,
              (missing) =>
                this.showBanner(
                  `${String(missing)} пар(ы) пропущены: значения признака недоступны (причина: нет данных метрик).`,
                  "warn",
                ),
            );
      const snapshot = await this.options.client.statistics.submit(
        this.detail.experiment.experiment_id,
        request,
      );
      const envelope = await pollStatisticsResult(this.options.client, snapshot.job_id, signal);
      renderComparisonEnvelope(this.resultHost, envelope);
      announcePolite("Результат сравнения получен");
    } catch (error) {
      if (!signal.aborted)
        this.showBanner(
          `Расчёт не выполнен: ${error instanceof Error ? error.message : String(error)}`,
          "error",
        );
    }
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
