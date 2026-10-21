/** Доменные типы ripple-сайдкара v1 (источник: src/lnt/ui/models_ripple.py +
 * analysis_v2/engine_ripple.py payload). Имена полей совпадают с JSON
 * бэкенда один в один. Недоступность — всегда явные null-скаляры и коды
 * причин; NaN/Infinity на проводе не существуют. Значения — наблюдаемые
 * диагностические вольты, не калиброванные DUT-вольты (provenance ниже). */

export type RippleAvailability = "available" | "unavailable";

export type RippleSessionSource = "device" | "synthetic";

export type RippleSettlingBasis = "capture_start_assuming_preconnected" | "settling_unknown";

export type RippleContinuityStatus = "synthetic_exact" | "host_contiguous_unverified";

export type RippleClippingAssessment =
  | "not_applicable_synthetic"
  | "no_rail_hits"
  | "rail_hits_present_localized"
  | "rail_hits_present_unlocalizable"
  | "clipping_unknown"
  | "clip_census_inconsistent";

export type RippleClipCountScope =
  | "aggregate_saved_record_telemetry"
  | "float32_endpoints_from_manifest_conversion";

export type RippleComponentBasis = "nominal" | "operator_measured";

export type RippleTransferStatus =
  | "nominal_transfer_declared"
  | "unavailable_unknown_probe_topology";

/** Идентичность алгоритма воспроизводимости (ripple_result.py). */
export interface RippleAlgorithm {
  id: "ripple_observed_v1";
  version: 1;
  rms: "population_centered_float64";
}

/** Запрошенные опции оценки: полоса и окно интервалов. */
export interface RippleOptions {
  band_low_hz: number;
  band_high_hz: number;
  interval_window_s: number;
}

/** Идентичность сессии с хэшами входов: сессия та же, пока хэши те же. */
export interface RippleSessionIdentity {
  session_id: string;
  manifest_sha256: string;
  ch1_sha256: string;
  channel: "ch1";
  source: RippleSessionSource;
}

/** Провенанс захвата против объявления оператора; калибровка — без
 * выдуманной идентичности: unknown = null. */
export interface RippleProvenance {
  capture_metadata_basis: "legacy_capture_metadata_not_adapter_provenance";
  operator_attachment: "preconnected_no_reconnection" | "settling_unknown";
  voltage_plane:
    | "synthetic_mathematical_volts"
    | "recorded_ch1_volts_observed_uncalibrated"
    | "recorded_ch1_volts_observed_calibration_identity_unknown";
  range_code: number;
  probe_multiplier: number;
  calibration_used: boolean | null;
  calibration_identity: string | null;
  hardware_qualification: "unverified";
}

/** Номинальная модель AC-адаптера: transfer — заявленный, не измеренный. */
export interface RippleAdapter {
  topology_id: "series_c_at_dut_tip_x1_v1";
  cap_nf: number;
  series_r_ohm: number;
  rin_ohm: number;
  probe_multiplier: number;
  component_values_basis: RippleComponentBasis;
  rail_nominal_v: number | null;
  fc_hz: number | null;
  tau_s: number | null;
  plateau_gain: number | null;
  transfer_status: RippleTransferStatus;
  assumption_codes: string[];
}

/** Исходные границы выбранного спана и база исключённого префикса. */
export interface RippleSelection {
  sample_start_index: number;
  sample_end_index_exclusive: number;
  sample_count: number;
  sample_rate_hz: number;
  realized_duration_s: number;
  excluded_prefix_samples: number;
  settling_prefix_samples_nominal: number;
  settling_basis: RippleSettlingBasis;
  continuity_status: RippleContinuityStatus;
  continuity_reason_codes: string[];
}

/** Ценз клиппинга/не-конечности выбранного спана; unknowable = null. */
export interface RippleQc {
  clipping_assessment: RippleClippingAssessment;
  clip_count_scope: RippleClipCountScope | null;
  clip_low_count: number | null;
  clip_high_count: number | null;
  nonfinite_count: number;
  nonfinite_count_scope: "selected_span";
  record_nonfinite_count: number;
  dropped_samples: number | null;
  reason_codes: string[];
}

/** Тайм-домен наблюдаемого плана: недоступно ⇒ числа null. */
export interface RippleTimeDomain {
  availability: RippleAvailability;
  reason_codes: string[];
  mean_v: number | null;
  rms_ac_v: number | null;
  vpp_v: number | null;
}

/** Один интервал: исходные границы, полнота, ценз и метрики. */
export interface RippleInterval {
  start_index: number;
  end_index_exclusive: number;
  sample_count: number;
  complete: boolean;
  realized_duration_s: number;
  availability: RippleAvailability;
  reason_codes: string[];
  clip_low_count: number | null;
  clip_high_count: number | null;
  mean_v: number | null;
  rms_ac_v: number | null;
  vpp_v: number | null;
}

/** Явные настройки Welch: доступность спектра не меняет их форму;
 * недоступные ветки фона несут пустой объект настроек. */
export interface RippleSpectrumSettings {
  nperseg?: number;
  max_chunk_samples?: number;
  overlap_fraction?: number;
  window?: string;
  detector?: string;
  detrend?: string;
  scaling?: string;
  resolution_hz?: number;
  enbw_hz?: number;
  segment_count?: number | null;
}

/** Спектр: доступен ⇒ три выровненные конечные серии; иначе серии пусты. */
export interface RippleSpectrum {
  availability: RippleAvailability;
  reason_codes: string[];
  settings: RippleSpectrumSettings;
  used_sample_count: number | null;
  ignored_tail_samples: number | null;
  frequency_hz: number[];
  psd_v2_per_hz: number[];
  asd_v_per_sqrt_hz: number[];
}

/** Хранимая полоса: доступна ⇒ центры и rms; недоступна ⇒ null при
 * сохранённых запрошенных границах. */
export interface RippleBand {
  id: string;
  low_hz: number;
  high_hz: number;
  first_center_hz: number | null;
  last_center_hz: number | null;
  bin_count: number | null;
  availability: RippleAvailability;
  reason_codes: string[];
  rms_v: number | null;
}

/** Фон РЯДОМ с измерением: собственные числа, сравнение без вычитания. */
export interface RippleBaseline {
  session: RippleSessionIdentity;
  attachment_basis: "same_adapter_tip_shorted_to_return" | null;
  comparison_status: RippleAvailability;
  reason_codes: string[];
  selection: RippleSelection | null;
  time_domain: RippleTimeDomain;
  spectrum: RippleSpectrum;
  bands: RippleBand[];
}

/** Полный сайдкар ripple.json v1 — байты, которые раздаёт GET-роут. */
export interface RippleArtifactPayload {
  schema_version: 1;
  algorithm: RippleAlgorithm;
  options: RippleOptions;
  session: RippleSessionIdentity;
  provenance: RippleProvenance;
  adapter: RippleAdapter;
  selection: RippleSelection;
  qc: RippleQc;
  time_domain: RippleTimeDomain;
  intervals: RippleInterval[];
  spectrum: RippleSpectrum;
  bands: RippleBand[];
  baseline: RippleBaseline | null;
}

/** Машинные коды причин 409 от GET /api/sessions/{id}/ripple. */
export type RippleConflictReason =
  | "corrupt"
  | "schema_incompatible"
  | "stale_input"
  | "unsafe_sidecar";

/** Дискриминатор типизированного отказа ripple-клиента. */
export type RippleErrorKind =
  | "not_built"
  | "not_found"
  | "conflict"
  | "invalid_request"
  | "network"
  | "parse"
  | "http";
