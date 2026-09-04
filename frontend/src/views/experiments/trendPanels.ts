/** Панели результата трендов (T11: выделено из trendView — было 257 чистых LOC).
 * Смешивающие факторы и маркировка descriptive_exploratory; только рендеры
 * из готовых данных, без сети и состояния. */

import type { TrendAnalysisResult } from "../../api/types-research";
import { el } from "../../components/primitives/dom";

export interface ConfoundItem {
  key: string;
  checked: boolean;
  note?: string | null;
}

/** Панель смешивающих факторов из confound_checklist эксперимента. */
export function renderConfoundPanel(checklist: ConfoundItem[]): HTMLElement {
  const panel = el("section", { className: "lnt-exp-confound lnt-exp-confound-host panel" });
  panel.append(el("h3", { className: "lnt-exp-subtitle", text: "Смешивающие факторы" }));
  if (checklist.length === 0) {
    panel.append(
      el("p", { className: "lnt-helper-text", text: "Чек-лист смешивающих факторов пуст." }),
    );
    return panel;
  }
  const list = el("ul", { className: "lnt-exp-limitations" });
  for (const item of checklist) {
    list.append(
      el("li", {
        text: `${item.key}: ${item.checked ? "проверен" : "НЕ проверен"}${item.note ? ` — ${item.note}` : ""}${item.checked ? "" : " · неконтролируемый смешивающий фактор делает связь неинтерпретируемой"}`,
      }),
    );
  }
  panel.append(list);
  return panel;
}

/** Маркировка результата: exploratory, единицы, N, запрет вымысла. */
export function renderLimitationsPanel(meta: TrendAnalysisResult["metadata"]): HTMLElement {
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
