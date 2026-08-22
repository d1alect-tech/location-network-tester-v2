/** Тренды и продольные ряды (todo 43): описательный запрос /trends/query,
 * uPlot-график наблюдений, панели смешивающих факторов и пропусков.
 * Результат сервера — descriptive_exploratory: причинность исключена. */

import type { LntApiClient } from "../../api/client";
import type { ObservationInput, TrendAnalysisResult } from "../../api/types-research";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";

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

function fmt(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(4) : "недоступно";
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
      className: "lnt-input",
      attrs: { type: "number", id: "lnt-trend-minn", "aria-label": "Минимальный N тренда" },
    });
    this.minNInput.value = "3";
    const runButton = el("button", {
      className: "lnt-btn lnt-btn-primary",
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
      el("div", { className: "lnt-exp-actions" }, [
        el("label", { className: "lnt-field-inline" }, [
          el("span", { className: "lnt-label-text", text: "Минимальный N" }),
          this.minNInput,
        ]),
        runButton,
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
    const meta = result.metadata;
    const qualityRaw = (result as Record<string, unknown>).data_quality;
    const quality =
      typeof qualityRaw === "object" && qualityRaw !== null
        ? (qualityRaw as Record<string, unknown>)
        : null;
    const trendsRaw = (result as Record<string, unknown>).trends;
    clearElement(this.resultHost);

    const status =
      meta.n < Math.max(minimumN, 5)
        ? "Мало данных: результат ограничен, интерпретация неустойчива."
        : "Достаточно данных для описательной сводки.";
    const banner = el("p", {
      className: `lnt-exp-banner ${meta.n < Math.max(minimumN, 5) ? "lnt-exp-banner-warn" : "lnt-exp-banner-info"}`,
      attrs: { role: "status" },
      text: status,
    });

    const grid = el("dl", { className: "lnt-exp-result-grid" });
    const pairs: [string, string][] = [
      ["Единицы", meta.units],
      ["Рецепт (estimator)", `${meta.estimator} · описательный`],
      ["N пригодных наблюдений", String(meta.n)],
    ];
    if (quality) {
      pairs.push(
        ["Входных наблюдений", String(quality.input_count ?? "недоступно")],
        ["Пропусков времени", String(quality.missing_timestamp_count ?? "недоступно")],
        [
          "Дубликатов (политика)",
          `${String(quality.duplicate_count ?? "недоступно")} · ${String(quality.dedupe_policy ?? "—")}`,
        ],
      );
    }
    for (const [term, definition] of pairs) {
      grid.append(el("dt", { text: term }), el("dd", { text: definition }));
    }

    const trendsList = el("ul", {
      className: "lnt-exp-limitations",
      attrs: { "aria-label": "Групповые средние" },
    });
    if (Array.isArray(trendsRaw)) {
      for (const trend of trendsRaw) {
        if (typeof trend !== "object" || trend === null) continue;
        const t = trend as Record<string, unknown>;
        trendsList.append(
          el("li", {
            text: `${String(t.group_dimension ?? "группа")}=${String(t.group_value ?? "—")}: N=${String(t.n ?? "?")}, среднее ${fmt(t.mean as number | null)} ${meta.units} (описательное, exploratory)`,
          }),
        );
      }
    }

    this.resultHost.append(
      banner,
      grid,
      el("h3", { className: "lnt-exp-subtitle", text: "Средние по группам (описательные)" }),
      trendsList,
      this.confoundPanel(),
      this.limitationsPanel(meta),
    );
  }

  /** Панель смешивающих факторов из confound_checklist эксперимента. */
  renderConfoundChecklist(
    checklist: { key: string; checked: boolean; note?: string | null }[],
  ): void {
    const host = this.root.querySelector(".lnt-exp-confound-host");
    host?.remove();
    if (checklist.length === 0) {
      return;
    }
    this.root.append(this.confoundPanel(checklist));
  }

  private confoundPanel(
    checklist?: { key: string; checked: boolean; note?: string | null }[],
  ): HTMLElement {
    const items = checklist ?? this.readConfoundFromRoot();
    const panel = el("section", { className: "lnt-exp-confound lnt-exp-confound-host" });
    panel.append(el("h3", { className: "lnt-exp-subtitle", text: "Смешивающие факторы" }));
    if (items.length === 0) {
      panel.append(
        el("p", { className: "lnt-helper-text", text: "Чек-лист смешивающих факторов пуст." }),
      );
      return panel;
    }
    const list = el("ul", { className: "lnt-exp-limitations" });
    for (const item of items) {
      list.append(
        el("li", {
          text: `${item.key}: ${item.checked ? "проверен" : "НЕ проверен"}${item.note ? ` — ${item.note}` : ""}${item.checked ? "" : " · неконтролируемый смешивающий фактор делает связь неинтерпретируемой"}`,
        }),
      );
    }
    panel.append(list);
    return panel;
  }

  private readConfoundFromRoot(): { key: string; checked: boolean; note?: string | null }[] {
    return [];
  }

  private limitationsPanel(meta: TrendAnalysisResult["metadata"]): HTMLElement {
    return el("div", { className: "lnt-exp-provenance" }, [
      el("h4", { className: "lnt-exp-provenance-title", text: "Маркировка результата" }),
      el("p", {
        className: "lnt-exp-meta-line",
        text: `Описательный разведочный анализ (exploratory). Единицы: ${meta.units} · N=${String(meta.n)}. Ранговые связи — корреляции, НЕ причинные эффекты.`,
      }),
      el("p", {
        className: "lnt-exp-meta-line",
        text: "Недостающие данные показаны как «недоступно» с кодом причины и никогда не восполняются вымыслом.",
      }),
    ]);
  }

  private showBanner(message: string, tone: "ok" | "warn" | "error"): void {
    const existing = this.root.querySelector(".lnt-exp-trend-status");
    existing?.remove();
    this.resultHost.before(
      el("p", {
        className: `lnt-exp-banner lnt-exp-banner-${tone} lnt-exp-trend-status`,
        attrs: tone === "error" ? { role: "alert" } : { role: "status" },
        text: message,
      }),
    );
  }
}
