/** Сводка видимого окна и CSV-альтернативы (todo 42): числовые сводки
 * band/time вместо только цвета, матрица текущего тайла и сводка окна.
 * NaN-ячейки считаются явно (coverage), а не молча пропускаются. */

import type { CandidateEventPayload } from "../../api/types-analysis";
import type { BandSummary, SpectrogramLevel, TileRequest, WindowSummary } from "./spectrogramModel";
import { levelValueAt, sliceTile } from "./spectrogramModel";

function formatRu(value: number): string {
  return value.toLocaleString("ru-RU", { maximumSignificantDigits: 8 });
}

/** Сводка видимого окна: диапазоны, статистика дБ, доля NaN без покрытия,
 * события в окне и топ-3 самых громких полос. */
export function summarizeWindow(
  level: SpectrogramLevel,
  request: TileRequest,
  events: readonly CandidateEventPayload[],
): WindowSummary {
  return summarizeSliced(sliceTile(level, request), events);
}

/** Сводка по УЖЕ нарезанному тайлу — без второй копии среза уровня. */
export function summarizeSliced(
  tile: { times: Float64Array; freqs: Float64Array; values: Float32Array },
  events: readonly CandidateEventPayload[],
): WindowSummary {
  const { times, freqs, values } = tile;
  let minDb = Number.POSITIVE_INFINITY;
  let maxDb = Number.NEGATIVE_INFINITY;
  let sum = 0;
  let finiteCount = 0;
  const bandSum = new Float64Array(freqs.length);
  const bandCount = new Uint32Array(freqs.length);
  for (let f = 0; f < freqs.length; f += 1) {
    for (let t = 0; t < times.length; t += 1) {
      const value = values[f * times.length + t] as number;
      if (!Number.isFinite(value)) continue;
      minDb = Math.min(minDb, value);
      maxDb = Math.max(maxDb, value);
      sum += value;
      finiteCount += 1;
      bandSum[f] = (bandSum[f] as number) + value;
      bandCount[f] = (bandCount[f] as number) + 1;
    }
  }
  const cells = times.length * freqs.length;
  const tStartS = times[0] ?? Number.NaN;
  const tEndS = times[times.length - 1] ?? Number.NaN;
  const eventCount = events.filter(
    (event) => event.peak_time_s >= tStartS && event.peak_time_s <= tEndS,
  ).length;
  const topBands: BandSummary[] = Array.from(freqs)
    .map((hz, f) => ({
      hz,
      db:
        (bandCount[f] as number) > 0
          ? (bandSum[f] as number) / (bandCount[f] as number)
          : Number.NaN,
    }))
    .filter((band) => Number.isFinite(band.db))
    .sort((a, b) => b.db - a.db)
    .slice(0, 3)
    .map((band) => ({ hz: band.hz, db: band.db }));
  return {
    tStartS,
    tEndS,
    fLowHz: freqs[0] ?? Number.NaN,
    fHighHz: freqs[freqs.length - 1] ?? Number.NaN,
    cells,
    minDb: finiteCount > 0 ? minDb : Number.NaN,
    maxDb: finiteCount > 0 ? maxDb : Number.NaN,
    meanDb: finiteCount > 0 ? sum / finiteCount : Number.NaN,
    nanShare: cells > 0 ? 1 - finiteCount / cells : 1,
    eventCount,
    topBands,
  };
}

/** Матрица тайла в длинной форме time_s,frequency_hz,power_db (bbox). */
export function tileMatrixCsv(level: SpectrogramLevel, request: TileRequest): string {
  const rows: string[] = ["time_s,frequency_hz,power_db"];
  for (let f = request.window.f0; f < request.window.f1; f += 1) {
    const hz = level.frequencyHz[f] as number;
    for (let t = request.window.t0; t < request.window.t1; t += 1) {
      rows.push(
        `${formatRu(level.timeS[t] as number)},${formatRu(hz)},${formatRu(levelValueAt(level, t, f))}`,
      );
    }
  }
  return rows.join("\n");
}

/** Сводка окна одной таблицей: параметры, статистика и топ-полосы. */
export function summaryCsv(summary: WindowSummary): string {
  const rows: string[] = ["parameter,value_ru"];
  const push = (name: string, value: string): void => {
    rows.push(`${name},${value}`);
  };
  push("окно_время_с", `${formatRu(summary.tStartS)}..${formatRu(summary.tEndS)}`);
  push("окно_полоса_Гц", `${formatRu(summary.fLowHz)}..${formatRu(summary.fHighHz)}`);
  push("ячеек", String(summary.cells));
  push("мин_дБ", formatRu(summary.minDb));
  push("макс_дБ", formatRu(summary.maxDb));
  push("среднее_дБ", formatRu(summary.meanDb));
  push("без_покрытия_доля", summary.nanShare.toFixed(4).replace(".", ","));
  push("событий_в_окне", String(summary.eventCount));
  for (const [index, band] of summary.topBands.entries()) {
    push(`топ_полоса_${index + 1}_Гц`, `${formatRu(band.hz)},${formatRu(band.db)}`);
  }
  return rows.join("\n");
}
