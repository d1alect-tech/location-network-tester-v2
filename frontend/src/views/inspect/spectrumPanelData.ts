import type { SessionDetailPayload, SpectrumPayload } from "../../api/types-plots";

export const EMPTY_SPECTRUM: SpectrumPayload = {
  frequency_hz: [],
  psd_v2_per_hz: [],
  point_count: 0,
};

function recordFromUnknown(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null) return null;
  const record: Record<string, unknown> = {};
  for (const key of Object.keys(value)) record[key] = Reflect.get(value, key);
  return record;
}

export function detailForPeaks(
  name: string,
  raw: { readonly analysis?: unknown },
): SessionDetailPayload {
  return {
    name,
    manifest: {},
    analysis: recordFromUnknown(raw.analysis),
    spectrum_available: true,
    waveform_available: false,
    ch2_available: false,
  };
}
