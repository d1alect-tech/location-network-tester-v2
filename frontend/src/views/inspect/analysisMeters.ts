/** Плитки-метры ленты анализа (выделено из analysisBand по политике
 * test_module_size — задача 10/D3): модель Meter, разбор detail и рендер
 * скалярных плиток. Причины «н/д» — из честных флагов detail, словарь
 * pairLoadOutcome (задача 9); рендер и тексты байт-в-байт прежние. */

import type { SessionDetailPayload } from "../../api/types-plots";
import { el } from "../../components/primitives/dom";
import { REASON_NO_ARTIFACT, REASON_UNAVAILABLE, branchNotComputedReason } from "./pairLoadOutcome";
import { isRecord, needleOf } from "./w1Parse";

export type Meter = {
  readonly label: string;
  readonly value: string;
  readonly unit?: string;
  /** Причина «н/д» (задача 9): из честных флагов detail, словарь pairLoadOutcome. */
  readonly reason?: string;
};

// «н/д» — ЗНАЧЕНИЕ отсутствия из единого словаря причин (задача 3, D2);
// пин analysisBand.test.ts живёт на значении, источник — pairLoadOutcome.
const UNAVAILABLE = REASON_UNAVAILABLE;
const WIDE_CHARS = 11;
const LONG_CHARS = 10;
const ruNumber = new Intl.NumberFormat("ru-RU");

function asFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatFixed(value: unknown, digits: number): string {
  const n = asFinite(value);
  return n === null ? UNAVAILABLE : n.toFixed(digits);
}

function formatCycles(value: unknown): string {
  const n = asFinite(value);
  return n === null ? UNAVAILABLE : String(n);
}

function formatBand(spectrum: Record<string, unknown> | null): string {
  if (spectrum === null) return UNAVAILABLE;
  const low = asFinite(spectrum.band_low_hz);
  const high = asFinite(spectrum.band_high_hz);
  if (low === null || high === null) return UNAVAILABLE;
  return `${ruNumber.format(low)}–${ruNumber.format(high)}`;
}

function formatResolution(spectrum: Record<string, unknown> | null): string {
  if (spectrum === null) return UNAVAILABLE;
  const n = asFinite(spectrum.resolution_hz);
  return n === null ? UNAVAILABLE : String(n);
}

function meter(label: string, value: string, unit?: string, reason?: string): Meter {
  if (reason === undefined) {
    return unit === undefined ? { label, value } : { label, value, unit };
  }
  return unit === undefined ? { label, value, reason } : { label, value, unit, reason };
}

/** Причина «н/д» игл: артефакт анализа отсутствует либо ветка не посчитана;
 * null-поля существующей ветки флаги не объясняют — причина не выдумывается. */
function needleAbsentReason(
  analysis: Record<string, unknown> | null,
  needle: Record<string, unknown> | null,
): string | undefined {
  if (needle !== null) return undefined;
  return analysis === null ? REASON_NO_ARTIFACT : branchNotComputedReason("");
}

/** Причина «н/д» полосы/разрешения: артефакт анализа отсутствует либо нет
 * spectrum.csv (честный флаг detail); иначе не посчитанная ветка метрик,
 * null-поля ветки не объясняются. */
function spectrumAbsentReason(
  detail: SessionDetailPayload,
  analysis: Record<string, unknown> | null,
  spectrum: Record<string, unknown> | null,
): string | undefined {
  if (spectrum !== null) return undefined;
  if (analysis === null || !detail.spectrum_available) return REASON_NO_ARTIFACT;
  return branchNotComputedReason("");
}

/** Плитки-заглушки без пары: подписи те же, значения «н/д» — факт отсутствия,
 * а не пустой ряд (эталон G6: лента читается в любом состоянии пары).
 * Причины нет: detail-пейлоада не существует, флаги нечему цитировать. */
export const EMPTY_METERS: readonly Meter[] = [
  meter("Частота сети", UNAVAILABLE, "Гц"),
  meter("μ иглы", UNAVAILABLE, "В"),
  meter("σ/μ", UNAVAILABLE),
  meter("P_async/P_sync", UNAVAILABLE),
  meter("Циклов", UNAVAILABLE),
  meter("Полоса", UNAVAILABLE, "Гц"),
  meter("Разрешение", UNAVAILABLE, "Гц"),
];

export function metersFromDetail(detail: SessionDetailPayload): Meter[] {
  const analysis = detail.analysis;
  const needle = isRecord(analysis) && isRecord(analysis.needle) ? analysis.needle : null;
  const spectrum = isRecord(analysis) && isRecord(analysis.spectrum) ? analysis.spectrum : null;
  const { sigma } = needleOf(analysis);
  const needleReason = needleAbsentReason(analysis, needle);
  const spectrumReason = spectrumAbsentReason(detail, analysis, spectrum);
  return [
    meter("Частота сети", formatFixed(needle?.line_frequency_hz, 7), "Гц", needleReason),
    meter("μ иглы", formatFixed(needle?.needle_mean_v, 4), "В", needleReason),
    meter("σ/μ", formatFixed(sigma, 3), undefined, needleReason),
    meter("P_async/P_sync", formatFixed(needle?.async_sync_ratio, 2), undefined, needleReason),
    meter(
      "Циклов",
      formatCycles(needle === null ? null : needle.cycles_analyzed),
      undefined,
      needleReason,
    ),
    meter("Полоса", formatBand(spectrum), "Гц", spectrumReason),
    meter("Разрешение", formatResolution(spectrum), "Гц", spectrumReason),
  ];
}

/** Плитка скаляра: подпись-капс + крупное моно-значение; длинное число
 * ступенью мельче и на две колонки, факт не усекается эллипсисом.
 * Причина «н/д» (задача 9, F-1) — ВИДИМЫЙ соседний узел
 * span.band-cell-reason ПОСЛЕ dd (стили — analysisBandReason.css, скоуп
 * .app-v6, только токены); текст dd байт-в-байт не меняется. title на dd —
 * бонусный дубликат словаря для наведения. */
export function scalarCell(item: Meter): HTMLElement {
  const valueEl = el("dd", {
    className: item.value.length > LONG_CHARS ? "is-long" : "",
    attrs: item.reason === undefined ? {} : { title: item.reason },
  });
  valueEl.append(item.value);
  if (item.unit !== undefined) {
    valueEl.append(el("span", { className: "t-unit", text: item.unit }));
  }
  const reasonEl =
    item.reason === undefined
      ? []
      : [
          el("span", {
            className: "band-cell-reason",
            text: item.reason,
            attrs: { "data-role": "band-reason", title: item.reason },
          }),
        ];
  const wide = item.value.length > WIDE_CHARS ? " is-wide" : "";
  return el("dl", { className: `band-cell${wide}` }, [
    el("dt", { text: item.label }),
    valueEl,
    ...reasonEl,
  ]);
}
