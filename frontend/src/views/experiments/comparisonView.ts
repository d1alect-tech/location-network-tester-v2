/** Панель сравнения (todo 43): проверка сравнимости → расчёт через durable
 * statistics-runs → результат с обязательной маркировкой. Гейт смешанных
 * типов блокирует расчёт с точной причиной; исключённые участники не
 * входят в пары; недостающие значения — явно с кодом причины.
 * C3: здесь только каркас, состояние и оркестрация — задачи в comparisonJobs,
 * построители запросов в comparisonRequests, отрисовка в comparisonResult,
 * слоты пары в comparisonGroups. */

import type { LntApiClient } from "../../api/client";
import type { ComparabilityReport, StatisticsRunRequest } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { renderPairbarSlots } from "./comparisonGroups";
import type { ComparisonBannerTone, ComparisonProtocolKind } from "./comparisonJobs";
import {
  runAnalysis as runAnalysisJob,
  runComparability as runComparabilityJob,
} from "./comparisonJobs";
import {
  buildAbaRequest,
  buildPairsRequest,
  effectFromPayload,
  groupedInProtocolOrder,
} from "./comparisonRequests";
import type { ComparisonResultTarget } from "./comparisonResult";
import { renderEnvelope, renderReport, showBanner } from "./comparisonResult";
import { protocolLabel } from "./experimentModel";
import type { ExperimentDetail } from "./experimentsStore";
import type { MemberRow } from "./memberTableView";
import type { EffectView } from "./resultPanel";

/** Реэкспорт для существующих импортов (driftDisplay.test.ts). */
export { effectFromPayload };
export type { EffectView };

/** Токены V6 для инлайнового баннера статуса (variantV6.css). */
const BANNER_TOKENS = "banner banner-inline";

interface RequestInput {
  kind: ComparisonProtocolKind;
  featureKey: string;
  units: string;
  seed: number;
  signal: AbortSignal;
}

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
    const plan = protocolLabel(String(detail.experiment.protocol.kind));
    this.pairbarHost.setAttribute("aria-label", `Пара условий: ${plan}`);
    if (this.featureInput.value === "") {
      this.featureInput.value = String(detail.experiment.primary_estimands?.[0]?.feature_key ?? "");
    }
    renderPairbarSlots(this.pairbarHost, this.rows, this.detail);
    this.renderIntro();
  }

  abort(): void {
    this.controller.abort();
  }

  async runComparability(): Promise<void> {
    const signal = this.restartController();
    await runComparabilityJob({
      client: this.options.client,
      detail: this.detail,
      signal,
      groupedInProtocolOrder: () => groupedInProtocolOrder(this.detail, this.rows),
      onReport: (report) => {
        this.lastReport = report;
      },
      showBanner: (message, tone) => {
        this.showBanner(message, tone);
      },
      renderReport: (report) => {
        renderReport(this.target, report);
      },
    });
  }

  async runAnalysis(featureKey: string, units: string, seed: number): Promise<void> {
    const signal = this.restartController();
    await runAnalysisJob({
      client: this.options.client,
      detail: this.detail,
      lastReport: this.lastReport,
      featureKey,
      units,
      seed,
      signal,
      buildStatisticsRequest: (kind, key, unit, seedValue, jobSignal) =>
        this.buildRequest({
          kind,
          featureKey: key,
          units: unit,
          seed: seedValue,
          signal: jobSignal,
        }),
      showBanner: (message, tone) => {
        this.showBanner(message, tone);
      },
      renderEnvelope: (envelope) => {
        renderEnvelope(this.target, envelope, effectFromPayload);
      },
    });
  }

  private get target(): ComparisonResultTarget {
    return {
      root: this.root,
      resultHost: this.resultHost,
      gateHost: this.gateHost,
      bannerClass: BANNER_TOKENS,
    };
  }

  private restartController(): AbortSignal {
    this.controller.abort();
    this.controller = new AbortController();
    return this.controller.signal;
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

  private async buildRequest(input: RequestInput): Promise<StatisticsRunRequest> {
    const shared = {
      detail: this.detail,
      rows: this.rows,
      featureKey: input.featureKey,
      units: input.units,
      seed: input.seed,
      signal: input.signal,
      valueSource: this.options.valueSource,
    };
    if (input.kind === "aba") return await buildAbaRequest(shared);
    return await buildPairsRequest({
      ...shared,
      kind: input.kind,
      notify: (message, tone) => {
        this.showBanner(message, tone);
      },
    });
  }

  private showBanner(message: string, tone: ComparisonBannerTone): void {
    showBanner(this.target, message, tone);
  }
}
