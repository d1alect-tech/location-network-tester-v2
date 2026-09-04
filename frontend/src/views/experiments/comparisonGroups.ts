/** Группировка участников панели сравнения (T11: выделено из comparisonView —
 * было 427 чистых LOC). Только чистая раскладка включённых участников по
 * условиям в порядке шагов протокола и отрисовка слотов pairbar; без сети,
 * без состояния, без слушателей. */

import { el } from "../../components/primitives/dom";
import type { ExperimentDetail } from "./experimentsStore";
import { currentState } from "./memberQc";
import type { MemberRow } from "./memberTableView";

/** Включённые участники по conditionId (исключённые не входят в пары). */
export function groupIncludedByCondition(rows: MemberRow[]): Map<string, MemberRow[]> {
  const map = new Map<string, MemberRow[]>();
  for (const row of rows) {
    if (currentState(row.inclusion) === "excluded") continue;
    const list = map.get(row.conditionId) ?? [];
    list.push(row);
    map.set(row.conditionId, list);
  }
  for (const list of map.values()) list.sort((a, b) => a.order - b.order);
  return map;
}

/** Условия в порядке шагов протокола (не по алфавиту): для A/B/A критично. */
export function orderConditions(detail: ExperimentDetail | null): string[] {
  const steps = detail?.experiment.steps ?? [];
  return [...steps]
    .sort((a, b) => Number(a.order) - Number(b.order))
    .map((step) => String(step.condition_id));
}

/** Группы включённых участников в порядке протокола. */
export function groupsInProtocolOrder(
  rows: MemberRow[],
  detail: ExperimentDetail | null,
): MemberRow[][] {
  const included = groupIncludedByCondition(rows);
  return orderConditions(detail)
    .map((conditionId) => included.get(conditionId) ?? [])
    .filter((group) => group.length > 0);
}

const PAIR_SLOT_LABELS = ["A", "Б", "A2"];

/** Полоса пары А—Б (для A/B/A — А1/Б/А2): только слоты условий и счётчики,
 * никакой числовой сводки — расчёт остаётся в resultHost. */
export function renderPairbarSlots(
  host: HTMLElement,
  rows: MemberRow[],
  detail: ExperimentDetail | null,
): void {
  host.replaceChildren();
  const included = groupIncludedByCondition(rows);
  for (const [index, conditionId] of orderConditions(detail).entries()) {
    const count = (included.get(conditionId) ?? []).length;
    host.append(
      el("div", { className: "pair-slot" }, [
        el("span", {
          className: "pair-role",
          text: PAIR_SLOT_LABELS[index] ?? `Слот ${String(index + 1)}`,
        }),
        el("span", { className: "pair-name", text: conditionId }),
        el("span", { className: "pair-meta", text: `N=${String(count)}` }),
      ]),
    );
  }
  host.append(el("span", { className: "pair-delta", text: "Δ —" }));
}
