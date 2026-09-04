export interface PeakFrequency {
  readonly frequencyHz: number;
}

export interface PeakDelta {
  readonly frequencyHz: number;
  readonly deltaDb: number | null;
}

function findNearestIndex(
  freqHz: readonly number[],
  targetHz: number
): number | null {
  if (freqHz.length === 0) {
    return null;
  }

  let nearestIdx = 0;
  let minDiff = Number.POSITIVE_INFINITY;

  for (let i = 0; i < freqHz.length; i++) {
    const f = freqHz[i];
    if (f !== undefined && Number.isFinite(f)) {
      const diff = Math.abs(f - targetHz);
      if (diff < minDiff) {
        minDiff = diff;
        nearestIdx = i;
      }
    }
  }

  return Number.isFinite(minDiff) ? nearestIdx : null;
}

function computeDeltaDb(
  psdAVal: number | undefined,
  psdBVal: number | undefined
): number | null {
  if (
    psdAVal === undefined ||
    psdBVal === undefined ||
    !Number.isFinite(psdAVal) ||
    !Number.isFinite(psdBVal) ||
    psdAVal <= 0 ||
    psdBVal <= 0
  ) {
    return null;
  }

  const delta = 10 * Math.log10(psdBVal / psdAVal);
  return Number.isFinite(delta) ? delta : null;
}

export function peakDeltas(
  freqHz: readonly number[],
  psdA: readonly number[],
  psdB: readonly number[],
  peaks: readonly PeakFrequency[]
): readonly PeakDelta[] {
  if (peaks.length === 0) {
    return [];
  }

  const result: PeakDelta[] = [];

  for (const peak of peaks) {
    const idx = findNearestIndex(freqHz, peak.frequencyHz);
    if (idx === null) {
      result.push({
        frequencyHz: peak.frequencyHz,
        deltaDb: null,
      });
      continue;
    }

    const a = psdA[idx];
    const b = psdB[idx];
    result.push({
      frequencyHz: peak.frequencyHz,
      deltaDb: computeDeltaDb(a, b),
    });
  }

  return result;
}
