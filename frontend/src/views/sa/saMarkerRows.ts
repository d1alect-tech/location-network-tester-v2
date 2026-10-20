/** Статические строки таблиц маркеров и пиков спектроанализатора. */

import type { LiveSaPeak } from "../../api/types-live";
import { el } from "../../components/primitives/dom";
import { formatDb, formatHz } from "./saUnits";

export function tableHead(labels: readonly string[]): HTMLElement {
  const head = el("thead");
  head.append(
    el(
      "tr",
      {},
      labels.map((label) => el("th", { text: label })),
    ),
  );
  return head;
}

export function peakRow(peak: LiveSaPeak): HTMLElement {
  return el("tr", {}, [
    el("td", { text: formatHz(peak.frequency_hz) }),
    el("td", { text: formatDb(peak.level_db) }),
    el("td", { text: formatDb(peak.prominence_db) }),
    el("td", {
      text:
        peak.q_factor === null || !Number.isFinite(peak.q_factor) ? "—" : peak.q_factor.toFixed(2),
    }),
  ]);
}
