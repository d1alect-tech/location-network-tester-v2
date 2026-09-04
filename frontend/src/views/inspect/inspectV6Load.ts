import type { SessionDetailPayload, SpectrumPayload } from "../../api/types-plots";
import type { Meter, PeakRow } from "./analysisBand";
import { metersFromDetail } from "./analysisBand";
import { peakDeltas } from "./peaksDelta";
import { isRecord } from "./w1Parse";

export type AnalysisBandClient = {
  readonly plots: {
    detail: (name: string) => Promise<SessionDetailPayload>;
    spectrum: (name: string) => Promise<SpectrumPayload>;
  };
};

type ParsedPeak = {
  readonly frequencyHz: number;
  readonly baseDb: number;
  readonly prominenceDb: number;
  readonly q: number;
};

function asFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parsePeak(value: unknown): ParsedPeak | null {
  if (!isRecord(value)) return null;
  const frequencyHz = asFinite(value.frequency_hz);
  const baseDb = asFinite(value.level_db);
  const prominenceDb = asFinite(value.prominence_db);
  const q = asFinite(value.q_factor);
  if (frequencyHz === null || baseDb === null || prominenceDb === null || q === null) {
    return null;
  }
  return { frequencyHz, baseDb, prominenceDb, q };
}

function peaksFromAnalysis(detail: SessionDetailPayload): ParsedPeak[] {
  const analysis = detail.analysis;
  if (!isRecord(analysis) || !isRecord(analysis.spectrum)) return [];
  const raw = analysis.spectrum.peaks;
  if (!Array.isArray(raw)) return [];
  const peaks: ParsedPeak[] = [];
  for (const item of raw) {
    const peak = parsePeak(item);
    if (peak !== null) peaks.push(peak);
  }
  return peaks;
}

function withDelta(peak: ParsedPeak, deltaDb: number | null): PeakRow {
  return {
    frequencyHz: peak.frequencyHz,
    baseDb: peak.baseDb,
    deltaDb,
    prominenceDb: peak.prominenceDb,
    q: peak.q,
  };
}

export async function loadAnalysisBand(
  client: AnalysisBandClient,
  a: string,
  b: string | null,
): Promise<{ meters: Meter[]; peaks: PeakRow[] }> {
  const detail = await client.plots.detail(a);
  const meters = metersFromDetail(detail);
  const parsed = peaksFromAnalysis(detail);
  if (b === null) {
    return { meters, peaks: parsed.map((peak) => withDelta(peak, null)) };
  }
  const [specA, specB] = await Promise.all([
    client.plots.spectrum(a),
    client.plots.spectrum(b),
  ]);
  const deltas = peakDeltas(
    specA.frequency_hz,
    specA.psd_v2_per_hz,
    specB.psd_v2_per_hz,
    parsed,
  );
  return {
    meters,
    peaks: parsed.map((peak, index) => withDelta(peak, deltas[index]?.deltaDb ?? null)),
  };
}
