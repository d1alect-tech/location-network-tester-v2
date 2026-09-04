/** B4 limit-lines: SEMI-F47/ITIC curves, user masks, verdict badges. Pure logic. */

export type LimitCurve = "itic" | "semi_f47";

export type LimitPoint = {
  readonly x: number;
  readonly y: number;
};

export type LimitMask = {
  readonly name: string;
  readonly unit: string;
  readonly points: readonly LimitPoint[];
};

export type MaskVerdict = "pass" | "fail" | "unavailable";

export type BadgeKind = MaskVerdict | "hidden" | "legacy";

/** ITIC 2000 envelope steps: [maxDurationS, lowFrac, highFrac]. */
export const ITIC_ENVELOPE: readonly (readonly [number, number, number])[] = [
  [0.02, 0.0, 1.2],
  [0.5, 0.7, 1.2],
  [10.0, 0.8, 1.1],
] as const;

export const ITIC_STEADY_BAND: readonly [number, number] = [0.9, 1.1] as const;

/** Simplified SEMI-F47 sag immunity: [maxDurationS, lowFrac, highFrac]. */
export const SEMI_F47_ENVELOPE: readonly (readonly [number, number, number])[] = [
  [0.2, 0.5, 1.1],
  [0.5, 0.7, 1.1],
  [1.0, 0.8, 1.1],
] as const;

export const SEMI_F47_STEADY_BAND: readonly [number, number] = [0.9, 1.1] as const;

function envelopeFor(durationS: number, curve: LimitCurve): readonly [number, number] | null {
  if (!Number.isFinite(durationS) || durationS < 0) return null;
  const steps = curve === "semi_f47" ? SEMI_F47_ENVELOPE : ITIC_ENVELOPE;
  const steady = curve === "semi_f47" ? SEMI_F47_STEADY_BAND : ITIC_STEADY_BAND;
  for (const [limit, low, high] of steps) {
    if (durationS <= limit + 1e-9) return [low, high];
  }
  return steady;
}

export function curveVerdict(
  durationS: number,
  ratio: number,
  curve: LimitCurve = "itic",
): MaskVerdict {
  if (!Number.isFinite(durationS) || !Number.isFinite(ratio) || durationS < 0) {
    return "unavailable";
  }
  const band = envelopeFor(durationS, curve);
  if (band === null) return "unavailable";
  const [low, high] = band;
  return low - 1e-9 <= ratio && ratio <= high + 1e-9 ? "pass" : "fail";
}

function interpolatedLimit(mask: LimitMask, x: number): number | null {
  const points = mask.points;
  const first = points[0];
  const last = points[points.length - 1];
  if (first === undefined || last === undefined) return null;
  if (x < first.x || x > last.x) return null;
  for (let i = 0; i < points.length - 1; i += 1) {
    const left = points[i];
    const right = points[i + 1];
    if (left === undefined || right === undefined) return null;
    if (left.x <= x && x <= right.x) {
      const span = right.x - left.x;
      if (span <= 0) return left.y;
      return left.y + ((x - left.x) / span) * (right.y - left.y);
    }
  }
  return x === last.x ? last.y : null;
}

export function evaluateMask(x: number, value: number, mask: LimitMask): MaskVerdict {
  if (!Number.isFinite(x) || !Number.isFinite(value)) return "unavailable";
  const limit = interpolatedLimit(mask, x);
  if (limit === null || !Number.isFinite(limit)) return "unavailable";
  return value <= limit ? "pass" : "fail";
}

export function spcVerdict(value: number, center: number, sigma: number, k = 3): MaskVerdict {
  if (!Number.isFinite(value) || !Number.isFinite(center)) return "unavailable";
  if (!Number.isFinite(sigma) || sigma <= 0 || !Number.isFinite(k) || k <= 0) {
    return "unavailable";
  }
  return Math.abs(value - center) <= k * sigma ? "pass" : "fail";
}

export function isValidMask(mask: LimitMask): boolean {
  if (mask.name.length === 0 || mask.unit.length === 0) return false;
  for (const point of mask.points) {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return false;
  }
  for (let i = 1; i < mask.points.length; i += 1) {
    const prev = mask.points[i - 1];
    const curr = mask.points[i];
    if (prev === undefined || curr === undefined) return false;
    if (!(curr.x > prev.x)) return false;
  }
  return true;
}

export function parseLimitMask(payload: unknown): LimitMask | null {
  if (typeof payload !== "object" || payload === null) return null;
  const record = payload as Record<string, unknown>;
  if (typeof record.name !== "string" || typeof record.unit !== "string") return null;
  if (!Array.isArray(record.points)) return null;
  const points: LimitPoint[] = [];
  for (const item of record.points) {
    if (typeof item !== "object" || item === null) return null;
    const row = item as Record<string, unknown>;
    if (typeof row.x !== "number" || typeof row.y !== "number") return null;
    points.push({ x: row.x, y: row.y });
  }
  const mask: LimitMask = { name: record.name, unit: record.unit, points };
  return isValidMask(mask) || mask.points.length === 0 ? mask : null;
}

export function badgeLabel(kind: BadgeKind): string {
  if (kind === "pass") return "PASS";
  if (kind === "fail") return "FAIL";
  if (kind === "hidden") return "HIDDEN";
  if (kind === "legacy") return "LEGACY";
  return "N/A";
}
