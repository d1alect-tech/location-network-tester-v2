/** APD bins table from apd.json. */

import { el } from "../../../components/primitives/dom";
import { formatScalar, isRecord } from "../w1Parse";
import { renderTable } from "./table";

export const APD_KIND = "apd";
export const APD_LABEL = "APD";

export type ApdBin = {
  readonly amplitudeV: number;
  readonly exceedanceProb: number;
  readonly levelDb: number;
};

export function parseApd(payload: unknown): readonly ApdBin[] | null {
  if (!isRecord(payload) || !Array.isArray(payload.apd)) return null;
  const rows: ApdBin[] = [];
  for (const item of payload.apd) {
    if (!isRecord(item)) continue;
    if (typeof item.amplitude_v !== "number") continue;
    if (typeof item.exceedance_prob !== "number") continue;
    if (typeof item.level_db !== "number") continue;
    rows.push({
      amplitudeV: item.amplitude_v,
      exceedanceProb: item.exceedance_prob,
      levelDb: item.level_db,
    });
  }
  return rows.length === 0 ? null : rows;
}

export function renderApd(body: HTMLElement, payload: unknown): void {
  const rows = parseApd(payload);
  if (rows === null) return;
  if (isRecord(payload) && typeof payload.apd_slope_db_per_decade === "number") {
    body.append(
      el("p", {
        className: "lnt-w1-panel-note",
        text: `slope ${formatScalar(payload.apd_slope_db_per_decade)} dB/decade`,
      }),
    );
  }
  renderTable(
    body,
    ["amplitude_v", "exceedance", "level_db"],
    rows.map((row) => [
      formatScalar(row.amplitudeV),
      formatScalar(row.exceedanceProb),
      formatScalar(row.levelDb),
    ]),
  );
}
