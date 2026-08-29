/** Audio 20Hz–3kHz peaks from audio_panel.json. */

import { el } from "../../../components/primitives/dom";
import { formatScalar, isRecord } from "../w1Parse";
import { renderTable } from "./table";

export const AUDIO_KIND = "audio";
export const AUDIO_LABEL = "Audio 20Hz–3kHz";

export type AudioPeak = {
  readonly frequencyHz: number;
  readonly prominence: number;
  readonly psd: number;
};

export type AudioView = {
  readonly lowHz: number;
  readonly highHz: number;
  readonly bandRmsV: number;
  readonly peaks: readonly AudioPeak[];
};

export function parseAudio(payload: unknown): AudioView | null {
  if (!isRecord(payload)) return null;
  if (typeof payload.low_hz !== "number") return null;
  if (typeof payload.high_hz !== "number") return null;
  if (typeof payload.band_rms_v !== "number") return null;
  if (!Array.isArray(payload.peaks)) return null;
  const peaks: AudioPeak[] = [];
  for (const item of payload.peaks) {
    if (!isRecord(item)) continue;
    if (typeof item.frequency_hz !== "number") continue;
    if (typeof item.prominence !== "number") continue;
    if (typeof item.psd_v2_per_hz !== "number") continue;
    peaks.push({
      frequencyHz: item.frequency_hz,
      prominence: item.prominence,
      psd: item.psd_v2_per_hz,
    });
  }
  return {
    lowHz: payload.low_hz,
    highHz: payload.high_hz,
    bandRmsV: payload.band_rms_v,
    peaks,
  };
}

export function renderAudio(body: HTMLElement, payload: unknown): void {
  const view = parseAudio(payload);
  if (view === null) return;
  body.append(
    el("p", {
      className: "lnt-w1-panel-note",
      text: `${formatScalar(view.lowHz)}–${formatScalar(view.highHz)} Hz, band_rms ${formatScalar(view.bandRmsV)} V`,
    }),
  );
  if (view.peaks.length === 0) return;
  renderTable(
    body,
    ["frequency_hz", "prominence", "psd"],
    view.peaks.map((peak) => [
      formatScalar(peak.frequencyHz),
      formatScalar(peak.prominence),
      formatScalar(peak.psd),
    ]),
  );
}
