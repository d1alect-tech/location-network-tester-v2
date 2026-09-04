/** ITIC / SEMI-F47 power-quality summary. Mount only for line_quality sessions. */

import { el } from "../../../components/primitives/dom";
import { curveVerdict } from "../limitLines";
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
  readonly semiF47Pass: number;
  readonly semiF47Fail: number;
  readonly semiF47Unavailable: number;
};

function semiF47Counts(payload: unknown): {
  readonly pass: number;
  readonly fail: number;
  readonly unavailable: number;
} {
  if (!isRecord(payload) || !Array.isArray(payload.events)) {
    return { pass: 0, fail: 0, unavailable: 0 };
  }
  let pass = 0;
  let fail = 0;
  let unavailable = 0;
  for (const item of payload.events) {
    if (!isRecord(item)) {
      unavailable += 1;
      continue;
    }
    const duration = item.duration_s;
    const depth = item.depth_pct;
    const kind = item.kind;
    if (typeof duration !== "number" || typeof depth !== "number" || typeof kind !== "string") {
      unavailable += 1;
      continue;
    }
    const ratio = kind === "swell" ? 1 + depth / 100 : 1 - depth / 100;
    const verdict = curveVerdict(duration, ratio, "semi_f47");
    if (verdict === "pass") pass += 1;
    else if (verdict === "fail") fail += 1;
    else unavailable += 1;
  }
  return { pass, fail, unavailable };
}

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
  const semi = semiF47Counts(payload);
  return {
    eventCount,
    rvcCount,
    halfCycleCount: summary.count,
    minRms: summary.min,
    maxRms: summary.max,
    nominalRms: summary.nominal_rms_v,
    semiF47Pass: semi.pass,
    semiF47Fail: semi.fail,
    semiF47Unavailable: semi.unavailable,
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
  const badge =
    view.semiF47Unavailable > 0 && view.eventCount > 0
      ? `SEMI-F47 N/A (${view.semiF47Unavailable})`
      : `SEMI-F47 PASS ${view.semiF47Pass} / FAIL ${view.semiF47Fail}`;
  row(dl, "semi_f47", badge);
  body.append(dl);
}
