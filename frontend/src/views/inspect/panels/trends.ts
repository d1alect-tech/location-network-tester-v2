/** Trends scalars from trends.json. */

import { el } from "../../../components/primitives/dom";
import { formatScalar, isRecord } from "../w1Parse";

export const TRENDS_KIND = "trends";
export const TRENDS_LABEL = "Trends";

export type TrendsView = {
  readonly crestFactor: number;
  readonly rmsV: number;
  readonly peakV: number;
  readonly slope: number;
  readonly intercept: number;
  readonly discardSamples: number;
  readonly eepromVerified: boolean;
  readonly changePoints: number;
};

export function parseTrends(payload: unknown): TrendsView | null {
  if (!isRecord(payload)) return null;
  if (typeof payload.crest_factor !== "number") return null;
  if (typeof payload.rms_v !== "number") return null;
  if (typeof payload.peak_v !== "number") return null;
  if (typeof payload.theil_sen_slope !== "number") return null;
  if (typeof payload.theil_sen_intercept !== "number") return null;
  if (typeof payload.discard_samples !== "number") return null;
  if (typeof payload.eeprom_verified !== "boolean") return null;
  const changePoints = Array.isArray(payload.change_points) ? payload.change_points.length : 0;
  return {
    crestFactor: payload.crest_factor,
    rmsV: payload.rms_v,
    peakV: payload.peak_v,
    slope: payload.theil_sen_slope,
    intercept: payload.theil_sen_intercept,
    discardSamples: payload.discard_samples,
    eepromVerified: payload.eeprom_verified,
    changePoints,
  };
}

function row(host: HTMLElement, label: string, value: string): void {
  host.append(el("div", {}, [el("dt", { text: label }), el("dd", { text: value })]));
}

export function renderTrends(body: HTMLElement, payload: unknown): void {
  const view = parseTrends(payload);
  if (view === null) return;
  const dl = el("dl", { className: "lnt-w1-scalars" });
  row(dl, "crest_factor", formatScalar(view.crestFactor));
  row(dl, "rms_v", formatScalar(view.rmsV));
  row(dl, "peak_v", formatScalar(view.peakV));
  row(dl, "theil_sen_slope", formatScalar(view.slope));
  row(dl, "theil_sen_intercept", formatScalar(view.intercept));
  row(dl, "discard_samples", String(view.discardSamples));
  row(dl, "eeprom_verified", String(view.eepromVerified));
  row(dl, "change_points", String(view.changePoints));
  body.append(dl);
}
