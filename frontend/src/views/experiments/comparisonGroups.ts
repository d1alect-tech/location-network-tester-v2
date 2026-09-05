/** Полоса пары панели сравнения (T11: выделено из comparisonView — было 427
 * чистых LOC; C3: раскладка по условиям переехала в comparisonRequests, здесь
 * остался только рендер слотов). Без сети, без состояния, без слушателей. */

import { el } from "../../components/primitives/dom";
import { includedByCondition, orderedConditions } from "./comparisonRequests";
import type { ExperimentDetail } from "./experimentsStore";
import type { MemberRow } from "./memberTableView";

const PAIR_SLOT_LABELS = ["A", "Б", "A2"];

/** Полоса пары А—Б (для A/B/A — А1/Б/А2): только слоты условий и счётчики,
 * никакой числовой сводки — расчёт остаётся в resultHost. */
export function renderPairbarSlots(
  host: HTMLElement,
  rows: MemberRow[],
  detail: ExperimentDetail | null,
): void {
  host.replaceChildren();
  const included = includedByCondition(rows);
  for (const [index, conditionId] of orderedConditions(detail).entries()) {
    const count = (included.get(conditionId) ?? []).length;
    const role = PAIR_SLOT_LABELS[index] ?? `Слот ${String(index + 1)}`;
    host.append(
      el(
        "div",
        {
          className: "pair-slot",
          attrs: {
            "data-condition": conditionId,
            title: `${role}: ${conditionId}, N=${String(count)}`,
          },
        },
        [
          el("span", { className: "pair-role", text: role }),
          el("span", { className: "pair-name", text: conditionId, attrs: { title: conditionId } }),
          el("span", { className: "pair-meta", text: `N=${String(count)}` }),
        ],
      ),
    );
  }
  host.append(el("span", { className: "pair-delta", text: "Δ —" }));
}
