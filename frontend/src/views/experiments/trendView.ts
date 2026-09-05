/** Тренды и продольные ряды (todo 43): описательный запрос /trends/query,
 * uPlot-график наблюдений, панели смешивающих факторов и пропусков.
 * Результат сервера — descriptive_exploratory: причинность исключена.
 * C1: панель смешивающих факторов — в trendConfoundPanel, сводка и
 * маркировка результата — в trendResultPanel; здесь сеть и состояние. */

import type { LntApiClient } from "../../api/client";
import type { ObservationInput, TrendAnalysisResult } from "../../api/types-research";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import type { TrendConfoundItem } from "./trendConfoundPanel";
import { buildTrendConfoundPanel, renderTrendConfoundChecklist } from "./trendConfoundPanel";
import { renderTrendResult } from "./trendResultPanel";

export interface TrendOptions {
  client: Pick<LntApiClient, "research">;
  /** Значение признака по сессии; null — недоступно (попадёт в пропуски). */
  valueSource?: (sessionId: string, signal: AbortSignal) => Promise<number | null>;
}

export interface TrendObservationRow {
  sessionId: string;
  condition: string;
  order: number;
  value: number | null;
  timestamp: string | null;
}

export class TrendView {
  readonly root: HTMLElement;
  private readonly client: Pick<LntApiClient, "research">;
  private resultHost: HTMLElement;
  private rows: TrendObservationRow[] = [];
  private units = "";
  private controller = new AbortController();
  private readonly minNInput: HTMLInputElement;
  private readonly valueSource:
    | ((sessionId: string, signal: AbortSignal) => Promise<number | null>)
    | null;

  constructor(options: TrendOptions) {
    this.client = options.client;
    this.valueSource = options.valueSource ?? null;
    this.minNInput = el("input", {
      className: "lnt-input ctl",
      attrs: { type: "number", id: "lnt-trend-minn", "aria-label": "Минимальный N тренда" },
    });
    this.minNInput.value = "3";
    const runButton = el("button", {
      className: "lnt-btn lnt-btn-primary btn",
      text: "Выполнить описательный запрос",
      attrs: { type: "button", id: "lnt-exp-run-trend" },
    });
    runButton.addEventListener(
      "click",
      () => void this.runQuery(Number(this.minNInput.value) || 3, 7),
    );
    this.resultHost = el("div", {});
    this.root = el("section", { className: "lnt-exp-trends" }, [
      el("h2", { className: "placeholder-title", text: "Тренды" }),
      el("p", {
        className: "lnt-helper-text",
        text: "Когортные и продольные ряды — только описательно (descriptive_exploratory). Связь ≠ причина.",
      }),
      el("div", { className: "lnt-exp-actions cmdbar" }, [
        el("div", { className: "cmd-fields" }, [
          el("label", { className: "lnt-field-inline field cmd-field" }, [
            el("span", {
              className: "lnt-label-text field-label cmd-label",
              text: "Минимальный N",
            }),
            this.minNInput,
          ]),
        ]),
        el("div", { className: "cmd-actions" }, [runButton]),
      ]),
      this.resultHost,
    ]);
  }

  setRows(rows: TrendObservationRow[], units: string): void {
    this.rows = rows;
    this.units = units;
    this.renderObservations();
  }

  abort(): void {
    this.controller.abort();
  }

  private renderObservations(): void {
    const usable = this.rows.filter((row) => row.value !== null);
    const missing = this.rows.length - usable.length;
    clearElement(this.resultHost);
    this.resultHost.append(
      el("p", {
        className: "lnt-exp-meta-line",
        text: `Наблюдений: ${String(this.rows.length)}, доступно значений: ${String(usable.length)}, недоступно: ${String(missing)}${missing > 0 ? " (причина: нет данных метрик — «недоступно»)" : ""}.`,
      }),
    );
  }

  async runQuery(minimumN: number, seed: number): Promise<void> {
    this.controller.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const observations: ObservationInput[] = [];
    let missing = 0;
    for (const row of this.rows) {
      let outcome: number | null = row.value;
      if (outcome === null && this.valueSource !== null && !signal.aborted) {
        outcome = await this.valueSource(row.sessionId, signal);
        row.value = outcome;
      }
      if (outcome === null) missing += 1;
      observations.push({
        observation_id: `obs-${row.sessionId}`,
        timestamp: row.timestamp,
        source_offset: `order:${String(row.order)}`,
        location: "site",
        condition: row.condition,
        predictor: row.order,
        outcome,
        metadata: [],
      });
    }
    if (missing > 0) {
      this.showBanner(
        `${String(missing)} наблюдений без значений — помечены «недоступно» и исключены из сводки.`,
        "warn",
      );
    }
    try {
      const result = await this.client.research.queryTrends(
        { observations, minimum_n: minimumN, units: this.units || "у.е.", seed },
        { signal },
      );
      this.renderResult(result, minimumN);
      announcePolite("Описательный трендовый анализ получен");
    } catch (error) {
      if (!signal.aborted) {
        this.showBanner(
          `Трендовый запрос не выполнен: ${error instanceof Error ? error.message : String(error)}`,
          "error",
        );
      }
    }
  }

  private renderResult(result: TrendAnalysisResult, minimumN: number): void {
    clearElement(this.resultHost);
    this.resultHost.append(...renderTrendResult(result, minimumN, buildTrendConfoundPanel([])));
  }

  /** Панель смешивающих факторов из confound_checklist эксперимента. */
  renderConfoundChecklist(checklist: TrendConfoundItem[]): void {
    renderTrendConfoundChecklist(this.root, checklist);
  }

  private showBanner(message: string, tone: "ok" | "warn" | "error"): void {
    const existing = this.root.querySelector(".lnt-exp-trend-status");
    existing?.remove();
    this.resultHost.before(
      el("p", {
        className: `lnt-exp-banner lnt-exp-banner-${tone} lnt-exp-trend-status banner banner-inline`,
        attrs: tone === "error" ? { role: "alert" } : { role: "status" },
        text: message,
      }),
    );
  }
}
