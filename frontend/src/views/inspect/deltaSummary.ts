/** U3: сигнатура пары — сводка Δ = 10·lg(B/A) по бинам спектра.
 *  Сетки A/B считаются индекс-совмещёнными (то же допущение, что peakDeltas);
 *  мусорные бины пропускаются, пустой итог — null, не нули. */

export interface DeltaSummary {
  readonly bins: number;
  readonly meanDb: number;
  readonly maxAbsDb: number;
}

const ruSigned = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});

/** «+0,3 дБ», «−1,2 дБ», «0,0 дБ». */
export function formatDeltaDb(value: number): string {
  return `${ruSigned.format(value)} дБ`;
}

export function summarizeDelta(
  psdA: readonly number[] | null | undefined,
  psdB: readonly number[] | null | undefined,
): DeltaSummary | null {
  if (psdA === null || psdA === undefined || psdB === null || psdB === undefined) return null;
  const n = Math.min(psdA.length, psdB.length);
  let sum = 0;
  let count = 0;
  let maxAbs = 0;
  for (let i = 0; i < n; i++) {
    const a = psdA[i];
    const b = psdB[i];
    if (typeof a !== "number" || typeof b !== "number") continue;
    if (!Number.isFinite(a) || !Number.isFinite(b) || a <= 0 || b <= 0) continue;
    const delta = 10 * Math.log10(b / a);
    if (!Number.isFinite(delta)) continue;
    sum += delta;
    count += 1;
    if (Math.abs(delta) > maxAbs) maxAbs = Math.abs(delta);
  }
  if (count === 0) return null;
  return { bins: count, meanDb: sum / count, maxAbsDb: maxAbs };
}
