/** Редактор гипотез (todo 43): формулировка, механизм, связи с estimand-ами
 * экспериментов, evidence-ссылки (result_id + descriptive_* kind), статусный
 * переход по автомату hypothesisState.ts. Ревизии — через PUT с
 * expected_revision (конфликт 409 показывается явно).
 * T11: форма и отправка — в hypothesisEditor; здесь список и состояние. */

import type { LntApiClient } from "../../api/client";
import type { HypothesisRecord } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import type { HypothesisLinkContext } from "./hypothesisEditor";
import { renderHypothesisEditor } from "./hypothesisEditor";
import { type HypothesisStatusValue, STATUS_LABELS_RU } from "./hypothesisState";

export interface HypothesisViewOptions {
  client: Pick<LntApiClient, "research">;
}

export class HypothesisView {
  readonly root: HTMLElement;
  private readonly client: Pick<LntApiClient, "research">;
  private listHost: HTMLElement;
  private editorHost: HTMLElement;
  private hypotheses: HypothesisRecord[] = [];
  /** Контекст эксперимента для связей: experiment_id → estimand. */
  linkContext: HypothesisLinkContext | null = null;

  constructor(options: HypothesisViewOptions) {
    this.client = options.client;
    this.listHost = el("div", {});
    this.editorHost = el("div", {});
    this.root = el("section", { className: "lnt-exp-hypotheses" }, [
      el("h2", { className: "placeholder-title", text: "Гипотезы" }),
      el("p", {
        className: "lnt-helper-text",
        text: "Утверждения со ссылками на доказательства (запуски расчётов). Статусы неcausal: «согласуется с наблюдениями» ≠ «доказано».",
      }),
      el("div", { className: "lnt-exp-actions cmdbar" }, [
        el("div", { className: "cmd-actions" }, [
          el("button", {
            className: "lnt-btn lnt-btn-primary btn",
            text: "Новая гипотеза…",
            attrs: { type: "button" },
          }),
        ]),
      ]),
      this.listHost,
      this.editorHost,
    ]);
    const newButton = this.root.querySelector("button");
    newButton?.addEventListener("click", () => this.renderEditor(null));
    void this.reload();
  }

  async reload(): Promise<void> {
    try {
      const page = await this.client.research.hypotheses({ page_size: 50 });
      this.hypotheses = page.items;
      this.renderList();
    } catch {
      this.listHost.replaceChildren(
        el("p", { className: "lnt-helper-text", text: "Список гипотез недоступен." }),
      );
    }
  }

  renderEditor(record: HypothesisRecord | null): void {
    renderHypothesisEditor(
      this.editorHost,
      {
        client: this.client,
        linkContext: this.linkContext,
        onSaved: () => this.reload(),
      },
      record,
    );
  }

  private renderList(): void {
    if (this.hypotheses.length === 0) {
      this.listHost.replaceChildren(
        el("p", { className: "lnt-helper-text", text: "Гипотез пока нет. Создайте первую." }),
      );
      return;
    }
    const list = el("ul", { className: "lnt-exp-hypothesis-list" });
    for (const record of this.hypotheses) {
      const status = record.status as HypothesisStatusValue;
      const item = el("li", { className: "lnt-exp-hypothesis-item" });
      item.append(
        el("strong", { text: record.statement }),
        el("span", {
          className: `lnt-status-pill ${status === "consistent_with_observations" ? "lnt-tone-ok" : status === "not_consistent" ? "lnt-tone-error" : "lnt-tone-warn"}`,
          text: `${record.status_label ?? STATUS_LABELS_RU[status] ?? status}`,
        }),
        el("button", {
          className: "lnt-btn lnt-btn-small btn-quiet",
          text: "Открыть",
          attrs: { type: "button", "aria-label": `Открыть гипотезу ${record.hypothesis_id}` },
        }),
      );
      const openButton = item.querySelector("button");
      openButton?.addEventListener("click", () => this.renderEditor(record));
      list.append(item);
    }
    this.listHost.replaceChildren(list);
  }
}
