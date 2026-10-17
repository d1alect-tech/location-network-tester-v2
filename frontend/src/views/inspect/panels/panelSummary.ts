/** Ключевое значение панели для свёрнутой шапки (G7 «Disclosure-панели»):
 * факт читается без раскрытия. Значения берутся из тех же парсеров, что и
 * тело панели, — второй математики здесь нет. null = значения нет, шапка
 * остаётся без цифры (никогда не 0 и не прочерк вместо факта). */

import { formatScalar, isRecord } from "../w1Parse";
import { parseApd } from "./apd";
import { parseAudio } from "./audio";
import { parseBurst } from "./burst";
import { parseCmDmCsv } from "./cmDm";
import { parseHarmonics } from "./harmonics";
import { iticBadge, parseItic } from "./itic";
import { parseNotching } from "./notching";
import { parseTrends } from "./trends";

export const APD_BINS_SUFFIX = "бинов";

function harmonicsKey(payload: unknown): string | null {
  const rows = parseHarmonics(payload);
  if (rows === null) return null;
  const mean = rows.reduce((sum, row) => sum + row.thd, 0) / rows.length;
  return `THD ${formatScalar(mean)}`;
}

function notchingKey(payload: unknown): string | null {
  const rows = parseNotching(payload);
  if (rows === null) return null;
  const peak = rows.reduce((max, row) => Math.max(max, row.depthV), 0);
  return `пик ${formatScalar(peak)} В`;
}

function apdKey(payload: unknown): string | null {
  const bins = parseApd(payload);
  if (bins === null) return null;
  const slope = isRecord(payload) ? payload.apd_slope_db_per_decade : null;
  if (typeof slope === "number") return `slope ${formatScalar(slope)} dB/dec`;
  return `${String(bins.length)} ${APD_BINS_SUFFIX}`;
}

function burstKey(payload: unknown): string | null {
  const view = parseBurst(payload);
  return view === null ? null : String(view.count);
}

function trendsKey(payload: unknown): string | null {
  const view = parseTrends(payload);
  return view === null ? null : `crest ${formatScalar(view.crestFactor)}`;
}

function audioKey(payload: unknown): string | null {
  const view = parseAudio(payload);
  return view === null ? null : `band_rms ${formatScalar(view.bandRmsV)} V`;
}

function iticKey(payload: unknown): string | null {
  const view = parseItic(payload);
  return view === null ? null : iticBadge(view);
}

function cmDmKey(text: unknown): string | null {
  if (typeof text !== "string") return null;
  const rows = parseCmDmCsv(text);
  return rows === null ? null : `${APD_BINS_SUFFIX}: ${String(rows.length)}`;
}

/** kind — тот же ключ, что и `data-panel` в panels/host.ts. */
export function panelKeyText(kind: string, payload: unknown): string | null {
  switch (kind) {
    case "harmonics":
      return harmonicsKey(payload);
    case "notching":
      return notchingKey(payload);
    case "apd":
      return apdKey(payload);
    case "burst":
      return burstKey(payload);
    case "trends":
      return trendsKey(payload);
    case "audio":
      return audioKey(payload);
    case "itic":
      return iticKey(payload);
    case "cm_dm":
      return cmDmKey(payload);
    default:
      return null;
  }
}
