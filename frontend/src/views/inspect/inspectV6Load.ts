import type { SessionDetailPayload } from "../../api/types-plots";
import { type Meter, type PeakRow, metersFromDetail } from "./analysisBand";
import type { DetailLoader } from "./pairDetail";
import { isRecord } from "./w1Parse";

export type AnalysisBandClient = {
  readonly plots: {
    detail: (
      name: string,
      options?: { readonly signal?: AbortSignal },
    ) => Promise<SessionDetailPayload>;
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

/** Загрузка ленты анализа (задача 10/D3): метры и пики из detail базы.
 * Δ пиков больше НЕ считается отдельным scope-фетчем — его кормит лента из
 * пейлоадов отображаемой плоскости (panel payloads, onPayloads), чтобы Δ
 * всегда был из той же плоскости, что график рядом. */
export async function loadAnalysisBand(
  client: AnalysisBandClient,
  a: string,
  signal?: AbortSignal,
  detail?: DetailLoader,
): Promise<{ meters: Meter[]; peaks: PeakRow[] }> {
  const loadDetail: DetailLoader =
    detail ?? ((name, options) => client.plots.detail(name, options));
  const payload = await loadDetail(a, { signal });
  const meters = metersFromDetail(payload);
  const parsed = peaksFromAnalysis(payload);
  return { meters, peaks: parsed.map((peak) => withDelta(peak, null)) };
}
