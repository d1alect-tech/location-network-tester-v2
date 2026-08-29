/** Burst list from burst.json. Empty list is honest, not a missing file. */

import { el } from "../../../components/primitives/dom";
import { formatScalar, isRecord } from "../w1Parse";
import { renderTable } from "./table";

export const BURST_KIND = "burst";
export const BURST_LABEL = "Burst";

export type BurstRow = {
  readonly startTimeS: number;
  readonly endTimeS: number;
  readonly peakV: number;
};

export type BurstView = {
  readonly count: number;
  readonly rows: readonly BurstRow[];
};

export function parseBurst(payload: unknown): BurstView | null {
  if (!isRecord(payload) || typeof payload.burst_count !== "number") return null;
  if (!Array.isArray(payload.bursts)) return { count: payload.burst_count, rows: [] };
  const rows: BurstRow[] = [];
  for (const item of payload.bursts) {
    if (!isRecord(item)) continue;
    const startTimeS = typeof item.start_time_s === "number" ? item.start_time_s : null;
    const endTimeS = typeof item.end_time_s === "number" ? item.end_time_s : null;
    const peakV = typeof item.peak_v === "number" ? item.peak_v : null;
    if (startTimeS === null || endTimeS === null || peakV === null) continue;
    rows.push({ startTimeS, endTimeS, peakV });
  }
  return { count: payload.burst_count, rows };
}

export function renderBurst(body: HTMLElement, payload: unknown): void {
  const view = parseBurst(payload);
  if (view === null) return;
  body.append(
    el("p", { className: "lnt-w1-panel-note", text: `burst_count ${String(view.count)}` }),
  );
  if (view.rows.length === 0) return;
  renderTable(
    body,
    ["start_s", "end_s", "peak_v"],
    view.rows.map((row) => [
      formatScalar(row.startTimeS),
      formatScalar(row.endTimeS),
      formatScalar(row.peakV),
    ]),
  );
}
