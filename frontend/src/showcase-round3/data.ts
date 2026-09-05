/** Данные раунда 3: пара A/B и её дельта поверх фикстур showcase-redesign.
 *  Табличная плоскость — числа PEAKS (реальный metrics.json); плоскость графика —
 *  генератор buildSpectrumData (та же пара сессий, иллюстративно). */
import { PEAKS, SESSIONS } from "../showcase-redesign/data";

export interface PairPeakRow {
  frequencyHz: number;
  aDb: number;
  bDb: number;
  deltaDb: number;
  q: number;
}

/** B = A + Δ; дельты согласованы с генератором спектра (пик 22,4 кГц демпфирован на 6 дБ). */
const DELTAS_DB: readonly number[] = [-6.02, -0.4, 0.11, -0.3, -0.5];

export const PAIR_PEAKS: readonly PairPeakRow[] = PEAKS.map((peak, index) => {
  const deltaDb = DELTAS_DB[index] ?? 0;
  return {
    frequencyHz: peak.frequencyHz,
    aDb: peak.levelDb,
    bDb: Math.round((peak.levelDb + deltaDb) * 100) / 100,
    deltaDb,
    q: peak.q,
  };
});

/** Маска: полоса и порог в табличной плоскости (дБ отн. 1 В²/Гц). */
export const LIMIT = {
  title: "Маска «розетка-порог»",
  bandLowHz: 18000,
  bandHighHz: 28000,
  limitDb: -50,
  marginDb: 2,
} as const;

export interface MaskVerdict {
  session: "A" | "B";
  pass: boolean;
  detail: string;
}

function verdictFor(session: "A" | "B"): MaskVerdict {
  const inBand = PAIR_PEAKS.filter(
    (row) => row.frequencyHz >= LIMIT.bandLowHz && row.frequencyHz <= LIMIT.bandHighHz,
  );
  const level = (row: PairPeakRow): number => (session === "A" ? row.aDb : row.bDb);
  const violations = inBand.filter((row) => level(row) > LIMIT.limitDb).length;
  return {
    session,
    pass: violations === 0,
    detail:
      violations === 0
        ? "все пики ниже лимита"
        : `${violations} пик выше лимита ${LIMIT.limitDb} дБ`,
  };
}

export const VERDICTS: readonly MaskVerdict[] = [verdictFor("A"), verdictFor("B")];

/** Сводные дельты пары для паирбара. */
export const PAIR_SUMMARY = {
  a: { id: SESSIONS[0]?.id ?? "", label: SESSIONS[0]?.label ?? "A" },
  b: { id: SESSIONS[1]?.id ?? "", label: SESSIONS[1]?.label ?? "B" },
  deltaPeakDb: -6.0,
  deltaPeakAtHz: 22418,
  deltaBandDb: -4.1,
  bandLowHz: 18000,
  bandHighHz: 28000,
} as const;

/** Маркеры: M1 на главном пике, M2 — дельта к M1 (стиль SDRangel). */
export const MARKERS = {
  m1: { frequencyHz: 22418.2, levelDb: -48.57 },
  m2DeltaHz: 5021.6,
  m2DeltaDb: -1.38,
} as const;

const nbsp = "\u00a0";

export function fmtDb(value: number, signed = false): string {
  const text = value.toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return signed && value > 0 ? `+${text}` : text;
}

export function fmtHz(value: number): string {
  if (value >= 1000) {
    const khz = (value / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
    return `${khz}${nbsp}кГц`;
  }
  return `${Math.round(value)}${nbsp}Гц`;
}
