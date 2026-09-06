/** U2: заливка channel-bar в inspect из spectrum-пейлоада и счётчиков анализа.
 *  Метка «Циклов» читается из meters loadAnalysisBand — та же строка, что в
 *  analysisBand, второго источника истины нет. */

import type { SpectrumPayload } from "../../api/types-plots";
import type { ChannelbarHandle } from "../../components/channelbar/channelbar";
import { formatBandRange, formatChannelRbw } from "../../components/channelbar/channelbar";
import type { Meter } from "./analysisBand";
import { MARKER_WINDOW_LABELS } from "./spectrumSelectors";

export function cyclesFromMeters(meters: readonly Meter[]): string | null {
  const found = meters.find((meter) => meter.label === "Циклов");
  const value = found?.value.trim();
  return value === undefined || value === "" ? null : value;
}

export function paintChannelbarFromPayload(
  bar: ChannelbarHandle,
  payload: SpectrumPayload | null,
  segments: string | null,
): void {
  bar.paint({
    band:
      payload === null
        ? null
        : formatBandRange(payload.band_low_hz ?? null, payload.band_high_hz ?? null),
    rbw: payload === null ? null : formatChannelRbw(payload.resolution_hz ?? null),
    window:
      payload?.window === undefined || payload.window === null
        ? null
        : (MARKER_WINDOW_LABELS[payload.window] ?? payload.window),
    detector: payload === null ? null : "Среднее",
    segments,
  });
}
