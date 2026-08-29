/** Notching events table from notching.json. */

import { formatScalar, isRecord } from "../w1Parse";
import { renderTable } from "./table";

export const NOTCHING_KIND = "notching";
export const NOTCHING_LABEL = "Notching";

export type NotchRow = {
  readonly startTimeS: number;
  readonly endTimeS: number;
  readonly depthV: number;
  readonly durationUs: number;
  readonly areaVUs: number;
};

export function parseNotching(payload: unknown): readonly NotchRow[] | null {
  if (!isRecord(payload) || !Array.isArray(payload.notches)) return null;
  const rows: NotchRow[] = [];
  for (const item of payload.notches) {
    if (!isRecord(item)) continue;
    if (typeof item.start_time_s !== "number") continue;
    if (typeof item.end_time_s !== "number") continue;
    if (typeof item.depth_v !== "number") continue;
    if (typeof item.duration_us !== "number") continue;
    if (typeof item.area_v_us !== "number") continue;
    rows.push({
      startTimeS: item.start_time_s,
      endTimeS: item.end_time_s,
      depthV: item.depth_v,
      durationUs: item.duration_us,
      areaVUs: item.area_v_us,
    });
  }
  return rows.length === 0 ? null : rows;
}

export function renderNotching(body: HTMLElement, payload: unknown): void {
  const rows = parseNotching(payload);
  if (rows === null) return;
  renderTable(
    body,
    ["start_s", "end_s", "depth_v", "duration_us", "area_v_us"],
    rows.map((row) => [
      formatScalar(row.startTimeS),
      formatScalar(row.endTimeS),
      formatScalar(row.depthV),
      formatScalar(row.durationUs),
      formatScalar(row.areaVUs),
    ]),
  );
}
