/** Finite scalar metrics exposed by the persisted v1 analysis payload. */
const METRIC_GROUPS = {
  needle: new Set([
    "cycles_analyzed",
    "line_frequency_hz",
    "needle_mean_v",
    "needle_sigma_ratio",
    "sync_power_v2",
    "async_power_v2",
    "async_sync_ratio",
    "lf_envelope_cv",
  ]),
  line_quality: new Set([
    "fundamental_hz",
    "fundamental_rms_v",
    "total_rms_v",
    "thd_ratio",
    "crest_factor",
    "envelope_cv",
    "cycles_analyzed",
  ]),
} as const;

const METRIC_UNITS: Record<string, string> = {
  needle_mean_v: "V",
  fundamental_rms_v: "V",
  total_rms_v: "V",
  sync_power_v2: "V^2",
  async_power_v2: "V^2",
  line_frequency_hz: "Hz",
  fundamental_hz: "Hz",
  cycles_analyzed: "dimensionless",
  needle_sigma_ratio: "dimensionless",
  async_sync_ratio: "dimensionless",
  lf_envelope_cv: "dimensionless",
  thd_ratio: "dimensionless",
  crest_factor: "dimensionless",
  envelope_cv: "dimensionless",
};

export interface SessionAnalysisLike {
  analysis: Record<string, unknown> | null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

export function knownMetricUnits(featureKey: string): string | null {
  const parts = featureKey.split(".");
  if (parts.length > 2) return null;
  if (parts.length === 2 && parts[0] !== "needle" && parts[0] !== "line_quality") return null;
  return METRIC_UNITS[parts.at(-1) ?? ""] ?? null;
}

/** Reads only shipped flat shapes and the two known persisted metric groups. */
export function sessionMetricValue(detail: SessionAnalysisLike, featureKey: string): number | null {
  const analysis = detail.analysis;
  if (analysis === null) return null;
  const flat = finite(record(analysis.metrics)?.[featureKey]) ?? finite(analysis[featureKey]);
  if (flat !== null) return flat;

  const parts = featureKey.split(".");
  const explicitGroup = parts.length === 2 ? parts[0] : null;
  const metricKey = parts.length === 2 ? parts[1] : featureKey;
  if (metricKey === undefined) return null;
  for (const groupName of ["needle", "line_quality"] as const) {
    if (explicitGroup !== null && explicitGroup !== groupName) continue;
    if (!METRIC_GROUPS[groupName].has(metricKey)) continue;
    const value = finite(record(analysis[groupName])?.[metricKey]);
    if (value !== null) return value;
  }
  return null;
}
