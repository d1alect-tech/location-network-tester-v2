/** Чистая модель панели «Риппл / шум»: сборка вида из СОХРАНЁННОГО
 * ripple.json v1. Никаких пересчётов: недоступное — null + причина,
 * полосы — только bands[], числа в data-value — байты артефакта. */

import type {
  RippleArtifactPayload,
  RippleAvailability,
  RippleBand,
  RippleTimeDomain,
} from "../../../api/types-ripple";
import {
  RIPPLE_DASH,
  SAMPLE_FORMAT,
  formatDuration,
  formatHzRange,
  formatVolts,
  reasonList,
} from "./rippleFormat";
import {
  type RippleBaselineView,
  baselineView,
  qcView,
  settlingChip,
  spectrumMeta,
  voltsChip,
} from "./rippleViewParts";

export {
  RIPPLE_DASH,
  formatDuration,
  formatHz,
  formatHzRange,
  formatVolts,
  reasonList,
  reasonText,
} from "./rippleFormat";
export type { RippleBaselineView, RippleQcView } from "./rippleViewParts";

export type RippleMetricKey = "mean" | "rms-ac" | "vpp" | "band";

export type RippleMetric = {
  readonly key: RippleMetricKey;
  readonly label: string;
  readonly note: string;
  readonly text: string;
  readonly raw: number | null;
  readonly reason: string | null;
};

export type RippleIntervalSlot = {
  readonly index: number | null;
  readonly text: string;
  readonly raw: number | null;
  readonly complete: boolean;
  readonly reason: string | null;
};

export type RippleBandOption = {
  readonly id: string;
  readonly label: string;
  readonly lowHz: number;
  readonly highHz: number;
};

export type RippleViewModel = {
  readonly state: "ready";
  readonly availability: RippleAvailability;
  readonly metrics: readonly RippleMetric[];
  readonly intervals: readonly RippleIntervalSlot[];
  readonly intervalCount: number;
  readonly intervalCountText: string;
  readonly bands: readonly RippleBandOption[];
  readonly selectedBand: number;
  readonly chips: readonly string[];
  readonly qcText: string;
  readonly qcTitle: string;
  readonly qcCodes: readonly string[];
  readonly qcOmitted: readonly string[];
  readonly baseline: RippleBaselineView;
  readonly spectrumAvailable: boolean;
  readonly spectrumAvailability: RippleAvailability;
  readonly spectrumText: string;
  readonly spectrumMeta: string;
  readonly durationText: string;
  readonly sampleText: string;
};

function metricReason(availability: RippleAvailability, raw: number | null, reasons: string[]) {
  if (availability === "unavailable") return reasonList(reasons);
  return raw === null ? "значение отсутствует" : null;
}

function bandOption(band: RippleBand): RippleBandOption {
  return {
    id: band.id,
    label: `${band.id} · ${formatHzRange(band.low_hz, band.high_hz)}`,
    lowHz: band.low_hz,
    highHz: band.high_hz,
  };
}

function metric(
  key: RippleMetricKey,
  label: string,
  note: string,
  raw: number | null,
  reason: string | null,
): RippleMetric {
  return { key, label, note, raw, text: formatVolts(raw), reason };
}

function intervalSlot(index: number, value: number | null, complete: boolean, reason: string) {
  return {
    index,
    text: value === null ? RIPPLE_DASH : formatVolts(value),
    raw: value,
    complete,
    reason: value === null ? reason : null,
  } satisfies RippleIntervalSlot;
}

function timeDomainReasons(td: RippleTimeDomain): string[] {
  return td.availability === "unavailable" ? [...td.reason_codes] : [];
}

/** Сборка вида: index полосы зажимается к сохранённому списку. */
export function buildRippleView(
  artifact: RippleArtifactPayload,
  bandIndex: number,
): RippleViewModel {
  const bands = artifact.bands.map(bandOption);
  const selectedBand =
    bands.length === 0 ? 0 : Math.min(Math.max(Math.trunc(bandIndex), 0), bands.length - 1);
  const band = artifact.bands[selectedBand] ?? null;
  const td = artifact.time_domain;
  const tdReasons = timeDomainReasons(td);
  const bandReasons = band === null ? ["band_missing"] : [...band.reason_codes];
  const bandAvailability = band?.availability ?? "unavailable";
  const intervalViews: RippleIntervalSlot[] = [];
  for (let index = 0; index < 3; index += 1) {
    const interval = artifact.intervals[index];
    if (interval === undefined) {
      intervalViews.push({ index: null, text: "—", raw: null, complete: false, reason: null });
      continue;
    }
    intervalViews.push(
      intervalSlot(
        index + 1,
        interval.vpp_v,
        interval.complete,
        interval.availability === "unavailable"
          ? reasonList(interval.reason_codes)
          : "значение отсутствует",
      ),
    );
  }
  const count = artifact.intervals.length;
  const spectrum = artifact.spectrum;
  const qc = qcView(artifact.qc, artifact.selection);
  const spectrumText =
    spectrum.availability === "available"
      ? ""
      : `спектр недоступен: ${reasonList(spectrum.reason_codes)}`;
  return {
    state: "ready",
    availability: td.availability,
    metrics: [
      metric(
        "mean",
        "Среднее",
        "по записи",
        td.mean_v,
        metricReason(td.availability, td.mean_v, tdReasons),
      ),
      metric(
        "rms-ac",
        "RMS AC",
        "полная запись",
        td.rms_ac_v,
        metricReason(td.availability, td.rms_ac_v, tdReasons),
      ),
      metric(
        "vpp",
        "Размах Vpp",
        "полный размах",
        td.vpp_v,
        metricReason(td.availability, td.vpp_v, tdReasons),
      ),
      metric(
        "band",
        "Полоса",
        band === null
          ? "полоса не сохранена"
          : `полоса ${formatHzRange(band.low_hz, band.high_hz)}`,
        band?.rms_v ?? null,
        band === null
          ? "полоса не сохранена"
          : metricReason(bandAvailability, band.rms_v, bandReasons),
      ),
    ],
    intervals: intervalViews,
    intervalCount: count,
    intervalCountText: count === 0 ? "нет окон" : `${count} окон`,
    bands,
    selectedBand,
    chips: [
      voltsChip(artifact),
      `программная полоса ${formatHzRange(artifact.options.band_low_hz, artifact.options.band_high_hz)}`,
      settlingChip(artifact.selection),
      artifact.selection.sample_count > 0
        ? `${SAMPLE_FORMAT.format(artifact.selection.sample_count)} отсчётов · ${formatDuration(artifact.selection.realized_duration_s)}`
        : "полных отсчётов нет",
    ],
    qcText: qc.text,
    qcTitle: qc.title,
    qcCodes: qc.codes,
    qcOmitted: qc.omitted,
    baseline: baselineView(artifact.baseline),
    spectrumAvailable: spectrum.availability === "available",
    spectrumAvailability: spectrum.availability,
    spectrumText,
    spectrumMeta: spectrumMeta(artifact),
    durationText: formatDuration(artifact.selection.realized_duration_s),
    sampleText: `${artifact.selection.sample_count} отсчётов · ${formatDuration(artifact.selection.realized_duration_s)}`,
  };
}
