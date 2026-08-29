/** Parse W1 inspect artifacts: pointer, THD windows, scalars, branch failures. */

import type { ThdWindow } from "./thdVerdict";

export const SCALAR = {
  thd: "THD-V",
  notch: "Peak Notch Depth",
  burst: "Burst Count",
  sigma: "σ_pk/μ_pk",
} as const;

export type ScalarKey = "thd-v" | "peak-notch-depth" | "burst-count" | "sigma-pk";

export type Scalar = {
  readonly key: ScalarKey;
  readonly label: string;
  readonly value: number;
};

export type BranchFailure = {
  readonly branch: string;
  readonly message: string;
};

export type Pointer = {
  readonly artifact_key: string;
};

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isPointer(value: unknown): value is Pointer {
  return isRecord(value) && typeof value.artifact_key === "string" && value.artifact_key.length > 0;
}

export function parseWindows(payload: unknown): readonly ThdWindow[] | null {
  if (!isRecord(payload) || !Array.isArray(payload.windows)) return null;
  const windows: ThdWindow[] = [];
  for (const item of payload.windows) {
    if (isRecord(item) && typeof item.thd === "number") windows.push({ thd: item.thd });
  }
  return windows.length === 0 ? null : windows;
}

export function peakNotch(payload: unknown): number | null {
  if (!isRecord(payload) || !Array.isArray(payload.notches)) return null;
  let peak: number | null = null;
  for (const item of payload.notches) {
    if (!isRecord(item) || typeof item.depth_v !== "number") continue;
    if (peak === null || item.depth_v > peak) peak = item.depth_v;
  }
  return peak;
}

export function burstCount(payload: unknown): number | null {
  if (!isRecord(payload) || typeof payload.burst_count !== "number") return null;
  return payload.burst_count;
}

export function needleOf(analysis: unknown): {
  readonly cycles: number;
  readonly sigma: number | null;
} {
  if (!isRecord(analysis) || !isRecord(analysis.needle)) return { cycles: 0, sigma: null };
  const cycles =
    typeof analysis.needle.cycles_analyzed === "number" ? analysis.needle.cycles_analyzed : 0;
  const sigma =
    typeof analysis.needle.needle_sigma_ratio === "number"
      ? analysis.needle.needle_sigma_ratio
      : null;
  return { cycles, sigma };
}

export function parseFailures(result: unknown): readonly BranchFailure[] {
  if (!isRecord(result) || !Array.isArray(result.branch_failures)) return [];
  const rows: BranchFailure[] = [];
  for (const item of result.branch_failures) {
    if (!isRecord(item) || typeof item.branch !== "string") continue;
    const message = typeof item.message === "string" ? item.message : "";
    rows.push({ branch: item.branch, message });
  }
  return rows;
}

export function formatScalar(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toPrecision(4);
}
