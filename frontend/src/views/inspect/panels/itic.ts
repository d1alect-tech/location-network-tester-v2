/** ITIC / power-quality summary. Mount only for line_quality sessions. */

import { el } from "../../../components/primitives/dom";
import { formatScalar, isRecord } from "../w1Parse";

export const ITIC_KIND = "itic";
export const ITIC_LABEL = "ITIC";

export type IticView = {
  readonly eventCount: number;
  readonly rvcCount: number;
  readonly halfCycleCount: number;
  readonly minRms: number;
  readonly maxRms: number;
  readonly nominalRms: number;
};

export function parseItic(payload: unknown): IticView | null {
  if (!isRecord(payload)) return null;
  const summary = payload.half_cycle_rms_summary;
  if (!isRecord(summary)) return null;
  if (typeof summary.count !== "number") return null;
  if (typeof summary.min !== "number") return null;
  if (typeof summary.max !== "number") return null;
  if (typeof summary.nominal_rms_v !== "number") return null;
  const eventCount = Array.isArray(payload.events) ? payload.events.length : 0;
  const rvcCount = Array.isArray(payload.rvc_events) ? payload.rvc_events.length : 0;
  return {
    eventCount,
    rvcCount,
    halfCycleCount: summary.count,
    minRms: summary.min,
    maxRms: summary.max,
    nominalRms: summary.nominal_rms_v,
  };
}

function row(host: HTMLElement, label: string, value: string): void {
  host.append(el("div", {}, [el("dt", { text: label }), el("dd", { text: value })]));
}

export function renderItic(body: HTMLElement, payload: unknown): void {
  const view = parseItic(payload);
  if (view === null) return;
  const dl = el("dl", { className: "lnt-w1-scalars" });
  row(dl, "events", String(view.eventCount));
  row(dl, "rvc_events", String(view.rvcCount));
  row(dl, "half_cycles", String(view.halfCycleCount));
  row(dl, "min_rms", formatScalar(view.minRms));
  row(dl, "max_rms", formatScalar(view.maxRms));
  row(dl, "nominal_rms", formatScalar(view.nominalRms));
  body.append(dl);
}
