/** Части вида панели ripple: фон рядом, QC-строка, честный ярлык вольт,
 * метаданные сохранённого спектра и подпись пустого слота графика.
 * Ни один помощник не считает измерение. */

import type {
  RippleArtifactPayload,
  RippleAvailability,
  RippleBaseline,
  RippleQc,
  RippleSelection,
} from "../../../api/types-ripple";
import type { RippleChartOutcome, RippleSpectrumMode } from "./rippleChart";
import {
  RIPPLE_DASH,
  SAMPLE_FORMAT,
  formatDuration,
  formatHz,
  formatVolts,
  reasonList,
  reasonText,
} from "./rippleFormat";
import { fitQcText } from "./rippleQcFit";

export type RippleBaselineView = {
  readonly status: "none" | RippleAvailability;
  readonly text: string;
  readonly rmsText: string;
  readonly vppText: string;
  readonly rmsRaw: number | null;
  readonly vppRaw: number | null;
  readonly session: string | null;
  readonly reasons: readonly string[];
};

export type RippleQcView = {
  readonly text: string;
  readonly title: string;
  readonly codes: readonly string[];
  readonly omitted: readonly string[];
  /** Коды, чей текст не попал в видимую строку: она о них честно сообщает. */
  readonly hidden: readonly string[];
};

export type ChartEmptyView = {
  readonly reason: string;
  readonly text: string;
  readonly title: string;
};

const CLIPPING: Readonly<Record<string, string>> = {
  not_applicable_synthetic: "синтетика",
  no_rail_hits: "рельсов нет",
  rail_hits_present_localized: "клиппинг локализован",
  rail_hits_present_unlocalizable: "клиппинг не локализован",
  clipping_unknown: "клиппинг неизвестен",
  clip_census_inconsistent: "ценз несогласован",
};

export function baselineView(baseline: RippleBaseline | null): RippleBaselineView {
  if (baseline === null) {
    return {
      status: "none",
      text: "Фон не приложен: сравнение не выполнялось.",
      rmsText: RIPPLE_DASH,
      vppText: RIPPLE_DASH,
      rmsRaw: null,
      vppRaw: null,
      session: null,
      reasons: [],
    };
  }
  const td = baseline.time_domain;
  const status = baseline.comparison_status;
  const text =
    status === "available"
      ? `Фон рядом: сравнение доступно, без вычитания (${baseline.session.session_id}).`
      : `Фон рядом: сравнение недоступно — ${reasonList(baseline.reason_codes)}. Числа фона показаны как записаны.`;
  return {
    status,
    text,
    rmsText: formatVolts(td.rms_ac_v),
    vppText: formatVolts(td.vpp_v),
    rmsRaw: td.rms_ac_v,
    vppRaw: td.vpp_v,
    session: baseline.session.session_id,
    reasons: baseline.reason_codes.map((code) => reasonText(code)),
  };
}

/** Машинные коды, факт которых строка QC уже показывает сама: оценка
 * клиппинга, счётчики рельсов и нечисловых отсчётов, непрерывность.
 * Повторять их — удлинять строку без новой информации; всё остальное
 * остаётся видимым дословно. */
function representedCodes(qc: RippleQc, selection: RippleSelection): Set<string> {
  const codes = new Set<string>([qc.clipping_assessment]);
  if ((qc.clip_low_count ?? 0) + (qc.clip_high_count ?? 0) > 0) codes.add("clipped");
  if (qc.nonfinite_count > 0) codes.add("nonfinite_samples");
  if (selection.continuity_status !== "synthetic_exact") {
    codes.add("host_contiguous_unverified");
    for (const code of selection.continuity_reason_codes) codes.add(code);
  }
  return codes;
}

/** QC-строка: видимый текст без дублей, в title — тот же текст плюс объём
 * ценза и ВСЕ машинные коды артефакта, поэтому сокращение ничего не прячет. */
export function qcView(qc: RippleQc, selection: RippleSelection): RippleQcView {
  const clip = `${qc.clip_low_count ?? RIPPLE_DASH}/${qc.clip_high_count ?? RIPPLE_DASH}`;
  const continuity =
    selection.continuity_status === "synthetic_exact" ? "точная" : "не подтверждена";
  const head = [
    CLIPPING[qc.clipping_assessment] ?? qc.clipping_assessment,
    `клиппинг ${clip}`,
    `нечисловые ${qc.nonfinite_count}`,
    `непрерывность ${continuity}`,
  ];
  const represented = representedCodes(qc, selection);
  const omitted: string[] = [];
  const entries: { text: string; codes: string[] }[] = [];
  for (const code of qc.reason_codes) {
    if (represented.has(code)) {
      omitted.push(code);
      continue;
    }
    const text = reasonText(code);
    const entry = entries.find((item) => item.text === text);
    if (entry === undefined) entries.push({ text, codes: [code] });
    else if (!entry.codes.includes(code)) entry.codes.push(code);
  }
  const fit = fitQcText(head, entries, represented, new Set(qc.reason_codes));
  const full =
    entries.length > 0 ? [...head, entries.map((entry) => entry.text).join(" · ")] : head;
  const scope = `ценз клиппинга: ${qc.clip_count_scope ?? RIPPLE_DASH} · нечисловые: ${qc.nonfinite_count_scope}`;
  const codes = `коды QC: ${qc.reason_codes.length === 0 ? "нет" : qc.reason_codes.join(", ")}`;
  return {
    text: fit.text,
    title: `QC: ${full.join(" · ")} · ${scope} · ${codes}`,
    codes: qc.reason_codes,
    omitted,
    hidden: fit.hidden,
  };
}

const ZERO_FLOOR_DETAIL: Readonly<Record<RippleSpectrumMode, string>> = {
  psd: "каждое сохранённое значение PSD равно 0 В²/Гц, а 10·lg(0) не определён",
  asd: "каждое сохранённое значение ASD равно 0 В/√Гц, а логарифмическая ось требует положительных значений",
};

/** Исход без графика: всё, кроме готового запроса. */
export type RippleChartEmptyOutcome = Exclude<RippleChartOutcome, { readonly kind: "request" }>;

/** Честная подпись пустого слота графика: доступный спектр никогда не
 * называется недоступным, нулевой уровень показан как нулевой уровень,
 * а неконечные значения не сериализуются ни в текст, ни в title. */
export function chartEmptyView(
  outcome: RippleChartEmptyOutcome,
  mode: RippleSpectrumMode,
  unavailableText: string,
): ChartEmptyView {
  if (outcome.kind === "unavailable") {
    const text = unavailableText === "" ? "спектр недоступен" : unavailableText;
    return { reason: "unavailable", text, title: text };
  }
  if (outcome.kind === "no_bins") {
    return {
      reason: "no_bins",
      text: "спектр сохранён без бинов",
      title: "Спектр доступен, но сохранённых бинов нет: точки для лог-оси брать неоткуда.",
    };
  }
  const bins = SAMPLE_FORMAT.format(outcome.bins);
  const zero = outcome.kind === "zero_floor";
  const detail = zero
    ? ZERO_FLOOR_DETAIL[mode]
    : "в сохранённых уровнях нет ни одной конечной положительной точки";
  return {
    reason: outcome.kind,
    text: zero
      ? `спектр сохранён · бинов ${bins} · уровни = 0 · точек на лог-оси нет`
      : `спектр сохранён · бинов ${bins} · точек на лог-оси нет`,
    title: `Спектр доступен и сохранён (бинов ${bins}): ${detail}, поэтому график не строится. Уровни не выдуманы и не заменены порогом.`,
  };
}

export function voltsChip(artifact: RippleArtifactPayload): string {
  switch (artifact.provenance.voltage_plane) {
    case "synthetic_mathematical_volts":
      return "математические вольты (синтетика)";
    case "recorded_ch1_volts_observed_calibration_identity_unknown":
      return "некалиброванные вольты · калибровка неизвестна";
    default:
      return "некалиброванные вольты";
  }
}

export function spectrumMeta(artifact: RippleArtifactPayload): string {
  const settings = artifact.spectrum.settings;
  const parts: string[] = [];
  if (settings.resolution_hz !== undefined) parts.push(`df ${formatHz(settings.resolution_hz)}`);
  if (settings.enbw_hz !== undefined) parts.push(`ENBW ${formatHz(settings.enbw_hz)}`);
  if (settings.segment_count !== undefined && settings.segment_count !== null) {
    parts.push(`${settings.segment_count} сегм.`);
  }
  return parts.length > 0 ? parts.join(" · ") : "настройки не сохранены";
}

export function settlingChip(selection: RippleSelection): string {
  if (selection.settling_basis === "settling_unknown") return "установление не подтверждено";
  const seconds =
    selection.sample_rate_hz > 0
      ? selection.excluded_prefix_samples / selection.sample_rate_hz
      : null;
  return `окно установления ${formatDuration(seconds)}`;
}
