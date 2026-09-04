import type { SpectrogramLevel } from "../../components/charts/spectrogramModel";

export type GramAlignResult =
  | { readonly kind: "ok"; readonly delta: Float32Array }
  | { readonly kind: "mismatch"; readonly code: "grid_mismatch" };

const GRID_MISMATCH: GramAlignResult = { kind: "mismatch", code: "grid_mismatch" };

function gridsMatch(left: Float64Array, right: Float64Array): boolean {
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

export function alignGramLevels(a: SpectrogramLevel, b: SpectrogramLevel): GramAlignResult {
  if (!gridsMatch(a.timeS, b.timeS) || !gridsMatch(a.frequencyHz, b.frequencyHz)) {
    return GRID_MISMATCH;
  }
  const delta = new Float32Array(a.powerDb.length);
  for (let i = 0; i < delta.length; i += 1) {
    delta[i] = (b.powerDb[i] ?? Number.NaN) - (a.powerDb[i] ?? Number.NaN);
  }
  return { kind: "ok", delta };
}
