/** Части вида панели ripple: фон рядом, QC-строка, честный ярлык вольт и
 * метаданные сохранённого спектра. Ни один помощник не считает измерение. */

import type {
  RippleArtifactPayload,
  RippleAvailability,
  RippleBaseline,
  RippleQc,
  RippleSelection,
} from "../../../api/types-ripple";
import {
  RIPPLE_DASH,
  formatDuration,
  formatHz,
  formatVolts,
  reasonList,
  reasonText,
} from "./rippleFormat";

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

export function qcText(qc: RippleQc, selection: RippleSelection): string {
  const clip = `${qc.clip_low_count ?? RIPPLE_DASH}/${qc.clip_high_count ?? RIPPLE_DASH}`;
  const continuity =
    selection.continuity_status === "synthetic_exact" ? "точная" : "не подтверждена";
  const parts = [
    CLIPPING[qc.clipping_assessment] ?? qc.clipping_assessment,
    `клиппинг ${clip}`,
    `NaN ${qc.nonfinite_count}`,
    `непрерывность ${continuity}`,
  ];
  if (qc.reason_codes.length > 0) parts.push(reasonList(qc.reason_codes));
  return `QC: ${parts.join(" · ")}`;
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
