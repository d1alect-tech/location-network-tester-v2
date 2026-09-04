/** UI-only THD-V limit check. Mean of harmonics windows vs 0.08. */

export const THD_V_LIMIT = 0.08;

export type ThdWindow = {
  readonly thd: number;
};

export type ThdVerdictInput = {
  readonly windows: readonly ThdWindow[] | null;
  readonly cyclesAnalyzed: number;
  readonly harmonicsFailed: boolean;
};

export type ThdVerdict =
  | { readonly kind: "pass"; readonly meanThd: number }
  | { readonly kind: "fail"; readonly meanThd: number }
  | { readonly kind: "hidden"; readonly meanThd: number | null }
  | { readonly kind: "legacy"; readonly meanThd: null };

function meanThd(windows: readonly ThdWindow[]): number {
  let sum = 0;
  for (const window of windows) sum += window.thd;
  return sum / windows.length;
}

export function thdVerdict(input: ThdVerdictInput, limit: number = THD_V_LIMIT): ThdVerdict {
  const mean = input.windows === null || input.windows.length === 0 ? null : meanThd(input.windows);
  if (input.harmonicsFailed) return { kind: "hidden", meanThd: mean };
  if (mean === null) return { kind: "legacy", meanThd: null };
  if (!Number.isFinite(limit) || limit <= 0) return { kind: "hidden", meanThd: mean };
  if (input.cyclesAnalyzed < 100) return { kind: "hidden", meanThd: mean };
  if (mean > limit) return { kind: "fail", meanThd: mean };
  return { kind: "pass", meanThd: mean };
}
