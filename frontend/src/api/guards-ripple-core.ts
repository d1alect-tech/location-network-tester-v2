/** Примитивы и блоки идентичности гвардов ripple.json v1.

Лист группы ripple (паттерн `client-research-*`): общие предикаты и проверки
идентичностей — алгоритм, опции, сессия, провенанс, адаптер, выбор спана и
QC-ценз. Форма зеркалирует `src/lnt/ui/models_ripple.py` и
`src/lnt/analysis_v2/ripple_result.py` один в один: новых полей нет.
Недоступность — всегда явные null и коды причин, никогда не нули по умолчанию.
*/

import type {
  RippleAdapter,
  RippleAlgorithm,
  RippleOptions,
  RippleProvenance,
  RippleQc,
  RippleSelection,
  RippleSessionIdentity,
} from "./types-ripple";

const SHA256_HEX = /^[0-9a-f]{64}$/;

const VOLTAGE_PLANES: readonly string[] = [
  "synthetic_mathematical_volts",
  "recorded_ch1_volts_observed_uncalibrated",
  "recorded_ch1_volts_observed_calibration_identity_unknown",
];
const CLIPPING_ASSESSMENTS: readonly string[] = [
  "not_applicable_synthetic",
  "no_rail_hits",
  "rail_hits_present_localized",
  "rail_hits_present_unlocalizable",
  "clipping_unknown",
  "clip_census_inconsistent",
];
const CLIP_COUNT_SCOPES: readonly string[] = [
  "aggregate_saved_record_telemetry",
  "float32_endpoints_from_manifest_conversion",
];
const SETTLING_BASES: readonly string[] = [
  "capture_start_assuming_preconnected",
  "settling_unknown",
];
const CONTINUITY_STATUSES: readonly string[] = ["synthetic_exact", "host_contiguous_unverified"];
const TRANSFER_STATUSES: readonly string[] = [
  "nominal_transfer_declared",
  "unavailable_unknown_probe_topology",
];

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function isNonnegativeInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

export function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function isFiniteNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => isFiniteNumber(item));
}

export function isSha256Hex(value: unknown): value is string {
  return typeof value === "string" && SHA256_HEX.test(value);
}

export function isEnum(values: readonly string[], value: unknown): boolean {
  return typeof value === "string" && values.includes(value);
}

export function isAlgorithm(value: unknown): value is RippleAlgorithm {
  if (!isRecord(value)) return false;
  return (
    value.id === "ripple_observed_v1" &&
    value.version === 1 &&
    value.rms === "population_centered_float64"
  );
}

export function isOptions(value: unknown): value is RippleOptions {
  if (!isRecord(value)) return false;
  if (!(isFiniteNumber(value.band_low_hz) && value.band_low_hz >= 0)) return false;
  if (!(isFiniteNumber(value.band_high_hz) && value.band_high_hz > value.band_low_hz)) {
    return false;
  }
  return isFiniteNumber(value.interval_window_s) && value.interval_window_s > 0;
}

export function isSessionIdentity(value: unknown): value is RippleSessionIdentity {
  if (!isRecord(value)) return false;
  if (typeof value.session_id !== "string" || value.session_id === "") return false;
  if (!isSha256Hex(value.manifest_sha256) || !isSha256Hex(value.ch1_sha256)) return false;
  if (value.channel !== "ch1") return false;
  return value.source === "device" || value.source === "synthetic";
}

/** Провенанс: объявление оператора против метаданных захвата; идентичность
 * калибровки неизвестна — null, а не выдуманное значение. */
export function isProvenance(value: unknown): value is RippleProvenance {
  if (!isRecord(value)) return false;
  if (value.capture_metadata_basis !== "legacy_capture_metadata_not_adapter_provenance") {
    return false;
  }
  if (
    value.operator_attachment !== "preconnected_no_reconnection" &&
    value.operator_attachment !== "settling_unknown"
  ) {
    return false;
  }
  if (!isEnum(VOLTAGE_PLANES, value.voltage_plane)) return false;
  if (!isNonnegativeInt(value.range_code)) return false;
  if (!(isFiniteNumber(value.probe_multiplier) && value.probe_multiplier > 0)) return false;
  if (value.calibration_used !== null && typeof value.calibration_used !== "boolean") {
    return false;
  }
  if (value.calibration_identity !== null && typeof value.calibration_identity !== "string") {
    return false;
  }
  return value.hardware_qualification === "unverified";
}

/** Номинальная модель адаптера: transfer заявлен, не измерен. */
export function isAdapter(value: unknown): value is RippleAdapter {
  if (!isRecord(value)) return false;
  if (value.topology_id !== "series_c_at_dut_tip_x1_v1") return false;
  if (!(isFiniteNumber(value.cap_nf) && value.cap_nf > 0)) return false;
  if (!(isFiniteNumber(value.series_r_ohm) && value.series_r_ohm >= 0)) return false;
  if (!(isFiniteNumber(value.rin_ohm) && value.rin_ohm > 0)) return false;
  if (!(isNonnegativeInt(value.probe_multiplier) && value.probe_multiplier >= 1)) return false;
  if (
    value.component_values_basis !== "nominal" &&
    value.component_values_basis !== "operator_measured"
  ) {
    return false;
  }
  if (value.rail_nominal_v !== null && !isFiniteNumber(value.rail_nominal_v)) return false;
  if (value.fc_hz !== null && !isFiniteNumber(value.fc_hz)) return false;
  if (value.tau_s !== null && !isFiniteNumber(value.tau_s)) return false;
  if (value.plateau_gain !== null && !isFiniteNumber(value.plateau_gain)) return false;
  if (!isEnum(TRANSFER_STATUSES, value.transfer_status)) return false;
  return isStringArray(value.assumption_codes);
}

/** Исходные границы спана: счётчик обязан совпасть с полуинтервалом. */
export function isSelection(value: unknown): value is RippleSelection {
  if (!isRecord(value)) return false;
  if (!isNonnegativeInt(value.sample_start_index)) return false;
  if (!isNonnegativeInt(value.sample_end_index_exclusive)) return false;
  if (value.sample_end_index_exclusive < value.sample_start_index) return false;
  if (
    !isNonnegativeInt(value.sample_count) ||
    value.sample_count !== value.sample_end_index_exclusive - value.sample_start_index
  ) {
    return false;
  }
  if (!(isFiniteNumber(value.sample_rate_hz) && value.sample_rate_hz > 0)) return false;
  if (!(isFiniteNumber(value.realized_duration_s) && value.realized_duration_s >= 0)) {
    return false;
  }
  if (!isNonnegativeInt(value.excluded_prefix_samples)) return false;
  if (!isNonnegativeInt(value.settling_prefix_samples_nominal)) return false;
  if (!isEnum(SETTLING_BASES, value.settling_basis)) return false;
  if (!isEnum(CONTINUITY_STATUSES, value.continuity_status)) return false;
  return isStringArray(value.continuity_reason_codes);
}

/** QC-ценз: unknowable остаётся null, нулём не подменяется. */
export function isQc(value: unknown): value is RippleQc {
  if (!isRecord(value)) return false;
  if (!isEnum(CLIPPING_ASSESSMENTS, value.clipping_assessment)) return false;
  if (value.clip_count_scope !== null && !isEnum(CLIP_COUNT_SCOPES, value.clip_count_scope)) {
    return false;
  }
  if (value.clip_low_count !== null && !isNonnegativeInt(value.clip_low_count)) return false;
  if (value.clip_high_count !== null && !isNonnegativeInt(value.clip_high_count)) return false;
  if (!isNonnegativeInt(value.nonfinite_count)) return false;
  if (value.nonfinite_count_scope !== "selected_span") return false;
  if (!isNonnegativeInt(value.record_nonfinite_count)) return false;
  if (value.dropped_samples !== null && !isNonnegativeInt(value.dropped_samples)) return false;
  return isStringArray(value.reason_codes);
}
