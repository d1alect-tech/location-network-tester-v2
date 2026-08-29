/** Harmonics windows table. Label is the CH1 HF-plane contract. */

import { el } from "../../../components/primitives/dom";
import { formatScalar, isRecord } from "../w1Parse";
import { renderTable } from "./table";

export const HARMONICS_KIND = "harmonics";
export const HARMONICS_LABEL = "CH1 HF plane, calibration_used=false, compare deltas";

export type HarmonicRow = {
  readonly index: number;
  readonly startTimeS: number;
  readonly thd: number;
  readonly fundamentalRms: number;
};

export function parseHarmonics(payload: unknown): readonly HarmonicRow[] | null {
  if (!isRecord(payload) || !Array.isArray(payload.windows)) return null;
  const rows: HarmonicRow[] = [];
  for (const item of payload.windows) {
    if (!isRecord(item)) continue;
    if (typeof item.thd !== "number") continue;
    const index = typeof item.index === "number" ? item.index : rows.length;
    const startTimeS = typeof item.start_time_s === "number" ? item.start_time_s : 0;
    const fundamentalRms =
      typeof item.fundamental_rms === "number" ? item.fundamental_rms : Number.NaN;
    if (!Number.isFinite(fundamentalRms)) continue;
    rows.push({ index, startTimeS, thd: item.thd, fundamentalRms });
  }
  return rows.length === 0 ? null : rows;
}

export function renderHarmonics(body: HTMLElement, payload: unknown): void {
  const rows = parseHarmonics(payload);
  if (rows === null) return;
  body.append(el("p", { className: "lnt-w1-panel-note", text: HARMONICS_LABEL }));
  renderTable(
    body,
    ["index", "start_s", "THD", "fund. RMS"],
    rows.map((row) => [
      String(row.index),
      formatScalar(row.startTimeS),
      formatScalar(row.thd),
      formatScalar(row.fundamentalRms),
    ]),
  );
}
