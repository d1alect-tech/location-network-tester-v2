/** Контракт-примеры гвардов ripple.json v1 (источник формы: models_ripple.py +
 * engine_ripple.py). Валидный сайдкар проходит; NaN/Infinity, чужие типы и
 * нарушенные инварианты «недоступно ⇒ null + коды причин» отбрасываются без
 * исключений и без подмены значений умолчаниями. */

import { describe, expect, it } from "vitest";
import { isRippleArtifact } from "./guards-ripple";
import type {
  RippleAdapter,
  RippleAlgorithm,
  RippleArtifactPayload,
  RippleBand,
  RippleBaseline,
  RippleInterval,
  RippleOptions,
  RippleProvenance,
  RippleQc,
  RippleSelection,
  RippleSessionIdentity,
  RippleSpectrum,
  RippleTimeDomain,
} from "./types-ripple";

const hex64 = (char: string): string => char.repeat(64);

const ALGORITHM: RippleAlgorithm = {
  id: "ripple_observed_v1",
  version: 1,
  rms: "population_centered_float64",
};
const OPTIONS: RippleOptions = { band_low_hz: 1, band_high_hz: 500, interval_window_s: 1 };
const SESSION: RippleSessionIdentity = {
  session_id: "syn-quiet-seed6022",
  manifest_sha256: hex64("f"),
  ch1_sha256: hex64("e"),
  channel: "ch1",
  source: "synthetic",
};
const PROVENANCE: RippleProvenance = {
  capture_metadata_basis: "legacy_capture_metadata_not_adapter_provenance",
  operator_attachment: "preconnected_no_reconnection",
  voltage_plane: "synthetic_mathematical_volts",
  range_code: 1,
  probe_multiplier: 1,
  calibration_used: null,
  calibration_identity: null,
  hardware_qualification: "unverified",
};
const ADAPTER: RippleAdapter = {
  topology_id: "series_c_at_dut_tip_x1_v1",
  cap_nf: 100,
  series_r_ohm: 0,
  rin_ohm: 1_000_000,
  probe_multiplier: 1,
  component_values_basis: "nominal",
  rail_nominal_v: 12,
  fc_hz: 1.5915494309189535,
  tau_s: 0.1,
  plateau_gain: 1,
  transfer_status: "nominal_transfer_declared",
  assumption_codes: ["one_pole_nominal_transfer", "component_values_nominal"],
};
const SELECTION: RippleSelection = {
  sample_start_index: 10_000,
  sample_end_index_exclusive: 40_000,
  sample_count: 30_000,
  sample_rate_hz: 10_000,
  realized_duration_s: 3,
  excluded_prefix_samples: 10_000,
  settling_prefix_samples_nominal: 10_000,
  settling_basis: "capture_start_assuming_preconnected",
  continuity_status: "synthetic_exact",
  continuity_reason_codes: [],
};
const QC: RippleQc = {
  clipping_assessment: "not_applicable_synthetic",
  clip_count_scope: null,
  clip_low_count: null,
  clip_high_count: null,
  nonfinite_count: 0,
  nonfinite_count_scope: "selected_span",
  record_nonfinite_count: 0,
  dropped_samples: 0,
  reason_codes: [],
};
const TIME_DOMAIN: RippleTimeDomain = {
  availability: "available",
  reason_codes: [],
  mean_v: 0.000005173322720890401,
  rms_ac_v: 0.002117531120011638,
  vpp_v: 0.021350678987801075,
};
const INTERVAL_COMPLETE: RippleInterval = {
  start_index: 10_000,
  end_index_exclusive: 20_000,
  sample_count: 10_000,
  complete: true,
  realized_duration_s: 1,
  availability: "available",
  reason_codes: [],
  clip_low_count: 0,
  clip_high_count: 0,
  mean_v: 0.000020597415163263122,
  rms_ac_v: 0.002106871774681803,
  vpp_v: 0.019981898367404938,
};
const INTERVAL_SHORT: RippleInterval = {
  start_index: 30_000,
  end_index_exclusive: 30_400,
  sample_count: 400,
  complete: false,
  realized_duration_s: 0.04,
  availability: "unavailable",
  reason_codes: ["insufficient_samples"],
  clip_low_count: null,
  clip_high_count: null,
  mean_v: null,
  rms_ac_v: null,
  vpp_v: null,
};
const SPECTRUM: RippleSpectrum = {
  availability: "available",
  reason_codes: [],
  settings: {
    nperseg: 10_000,
    max_chunk_samples: 1_000_000,
    overlap_fraction: 0.5,
    window: "hann",
    detector: "mean",
    detrend: "constant",
    scaling: "density",
    resolution_hz: 1,
    enbw_hz: 1.5,
    segment_count: 5,
  },
  used_sample_count: 30_000,
  ignored_tail_samples: 0,
  frequency_hz: [0, 1, 2],
  psd_v2_per_hz: [7.40658967308813e-11, 5.662041868960643e-10, 3.6018572984358953e-10],
  asd_v_per_sqrt_hz: [8.605e-6, 2.379e-5, 1.898e-5],
};
/** Недоступный спектр ветки фона: настройки — пустой объект (engine_ripple.py). */
const SPECTRUM_UNAVAILABLE: RippleSpectrum = {
  availability: "unavailable",
  reason_codes: ["settling_unknown"],
  settings: {},
  used_sample_count: null,
  ignored_tail_samples: null,
  frequency_hz: [],
  psd_v2_per_hz: [],
  asd_v_per_sqrt_hz: [],
};
const BAND: RippleBand = {
  id: "ripple",
  low_hz: 1,
  high_hz: 500,
  first_center_hz: 1,
  last_center_hz: 500,
  bin_count: 500,
  availability: "available",
  reason_codes: [],
  rms_v: 0.0006369719075516393,
};
const BAND_UNAVAILABLE: RippleBand = {
  id: "ripple",
  low_hz: 1,
  high_hz: 500,
  first_center_hz: null,
  last_center_hz: null,
  bin_count: null,
  availability: "unavailable",
  reason_codes: ["settling_unknown"],
  rms_v: null,
};

const VALID: RippleArtifactPayload = {
  schema_version: 1,
  algorithm: ALGORITHM,
  options: OPTIONS,
  session: SESSION,
  provenance: PROVENANCE,
  adapter: ADAPTER,
  selection: SELECTION,
  qc: QC,
  time_domain: TIME_DOMAIN,
  intervals: [INTERVAL_COMPLETE, INTERVAL_SHORT],
  spectrum: SPECTRUM,
  bands: [BAND],
  baseline: null,
};

const clone = (): RippleArtifactPayload => structuredClone(VALID);

/** Копия блока без указанного ключа: ключ действительно отсутствует в JSON. */
function omitKey(block: object, key: string): Record<string, unknown> {
  return Object.fromEntries(Object.entries(block).filter(([name]) => name !== key));
}

/** Мутация числового поля в строку: нарушение типа, а не схемы. */
function withString(block: object, key: string, text: string): Record<string, unknown> {
  const copy: Record<string, unknown> = Object.fromEntries(Object.entries(block));
  copy[key] = text;
  return copy;
}

describe("isRippleArtifact: валидные формы", () => {
  it("принимает сохранённый сайдкар v1 целиком", () => {
    expect(isRippleArtifact(VALID)).toBe(true);
  });

  it("принимает device-артефакт с недоступными ветками и null-скалярами", () => {
    const artifact = clone();
    artifact.session.source = "device";
    artifact.provenance.voltage_plane = "recorded_ch1_volts_observed_uncalibrated";
    artifact.provenance.calibration_used = false;
    artifact.provenance.calibration_identity = "legacy_bit_identical_conversion";
    artifact.provenance.operator_attachment = "settling_unknown";
    artifact.selection.continuity_status = "host_contiguous_unverified";
    artifact.selection.continuity_reason_codes = ["host_contiguous_unverified"];
    artifact.selection.settling_basis = "settling_unknown";
    artifact.qc.clipping_assessment = "clipping_unknown";
    artifact.qc.dropped_samples = null;
    artifact.time_domain = {
      availability: "unavailable",
      reason_codes: ["settling_unknown"],
      mean_v: null,
      rms_ac_v: null,
      vpp_v: null,
    };
    artifact.spectrum = SPECTRUM_UNAVAILABLE;
    artifact.bands = [BAND_UNAVAILABLE];
    expect(isRippleArtifact(artifact)).toBe(true);
  });

  it("принимает сравнение с фоном: числа рядом, статус сравнения явный", () => {
    const baseline: RippleBaseline = {
      session: {
        session_id: "syn-quiet-seed6024",
        manifest_sha256: hex64("a"),
        ch1_sha256: hex64("b"),
        channel: "ch1",
        source: "synthetic",
      },
      attachment_basis: "same_adapter_tip_shorted_to_return",
      comparison_status: "unavailable",
      reason_codes: ["baseline_sample_rate_mismatch"],
      selection: null,
      time_domain: {
        availability: "unavailable",
        reason_codes: ["baseline_sample_rate_mismatch"],
        mean_v: null,
        rms_ac_v: null,
        vpp_v: null,
      },
      spectrum: {
        ...SPECTRUM_UNAVAILABLE,
        reason_codes: ["baseline_sample_rate_mismatch"],
      },
      bands: [{ ...BAND_UNAVAILABLE, reason_codes: ["baseline_sample_rate_mismatch"] }],
    };
    expect(isRippleArtifact({ ...clone(), baseline })).toBe(true);
  });

  it("сохраняет недоступные поля как null и не подменяет их значениями", () => {
    const artifact = clone();
    artifact.bands = [{ ...BAND_UNAVAILABLE, low_hz: 99, high_hz: 101 }];
    artifact.spectrum = SPECTRUM_UNAVAILABLE;
    expect(isRippleArtifact(artifact)).toBe(true);
    expect(artifact.bands[0]?.low_hz).toBe(99);
    expect(artifact.bands[0]?.rms_v).toBeNull();
    expect(artifact.bands[0]?.bin_count).toBeNull();
    // Опциональные ключи настроек остаются ОТСУТСТВУЮЩИМИ, а не нулевыми.
    expect(Object.keys(artifact.spectrum.settings)).toEqual([]);
  });

  it("не изменяет проверяемый payload", () => {
    const artifact = clone();
    const before = JSON.stringify(artifact);
    expect(isRippleArtifact(artifact)).toBe(true);
    expect(JSON.stringify(artifact)).toBe(before);
  });
});

describe("isRippleArtifact: каркас и идентичности", () => {
  it("отбрасывает не-объекты", () => {
    expect(isRippleArtifact(null)).toBe(false);
    expect(isRippleArtifact("ripple")).toBe(false);
    expect(isRippleArtifact([])).toBe(false);
    expect(isRippleArtifact(undefined)).toBe(false);
  });

  it("отбрасывает чужой набор ключей верхнего уровня", () => {
    expect(isRippleArtifact(omitKey(clone(), "qc"))).toBe(false);
    expect(isRippleArtifact({ ...clone(), unexpected: true })).toBe(false);
  });

  it("отбрасывает не-v1 схему и чужой алгоритм", () => {
    expect(isRippleArtifact({ ...clone(), schema_version: 2 })).toBe(false);
    expect(isRippleArtifact({ ...clone(), schema_version: "1" })).toBe(false);
    expect(isRippleArtifact({ ...clone(), algorithm: { ...ALGORITHM, id: "ripple_dut_v2" } })).toBe(
      false,
    );
    expect(
      isRippleArtifact({ ...clone(), algorithm: { ...ALGORITHM, rms: "sample_two_pass" } }),
    ).toBe(false);
    expect(isRippleArtifact({ ...clone(), algorithm: { ...ALGORITHM, version: 2 } })).toBe(false);
  });

  it("отбрасывает чужой канал, источник и не-hex хэши", () => {
    expect(isRippleArtifact({ ...clone(), session: { ...SESSION, channel: "ch2" } })).toBe(false);
    expect(isRippleArtifact({ ...clone(), session: { ...SESSION, source: "emu" } })).toBe(false);
    expect(
      isRippleArtifact({ ...clone(), session: { ...SESSION, manifest_sha256: hex64("Z") } }),
    ).toBe(false);
    expect(isRippleArtifact({ ...clone(), session: { ...SESSION, ch1_sha256: "nothex" } })).toBe(
      false,
    );
  });
});

describe("isRippleArtifact: конечные числа и опции", () => {
  it("отбрасывает NaN и Infinity в числовых полях", () => {
    expect(isRippleArtifact({ ...clone(), options: { ...OPTIONS, band_low_hz: Number.NaN } })).toBe(
      false,
    );
    expect(
      isRippleArtifact({
        ...clone(),
        options: { ...OPTIONS, band_high_hz: Number.POSITIVE_INFINITY },
      }),
    ).toBe(false);
    const infiniteMetric = clone();
    infiniteMetric.time_domain.rms_ac_v = Number.NEGATIVE_INFINITY;
    expect(isRippleArtifact(infiniteMetric)).toBe(false);
    const nanSpectrum = clone();
    nanSpectrum.spectrum.psd_v2_per_hz = [1e-10, Number.NaN];
    expect(isRippleArtifact(nanSpectrum)).toBe(false);
    expect(
      isRippleArtifact({ ...clone(), selection: { ...SELECTION, sample_rate_hz: Number.NaN } }),
    ).toBe(false);
    expect(isRippleArtifact({ ...clone(), adapter: { ...ADAPTER, tau_s: Number.NaN } })).toBe(
      false,
    );
  });

  it("отбрасывает строки вместо чисел и нарушенную полосу опций", () => {
    expect(
      isRippleArtifact({ ...clone(), options: withString(OPTIONS, "interval_window_s", "1") }),
    ).toBe(false);
    expect(isRippleArtifact({ ...clone(), options: { ...OPTIONS, band_high_hz: 1 } })).toBe(false);
    expect(isRippleArtifact({ ...clone(), options: { ...OPTIONS, interval_window_s: 0 } })).toBe(
      false,
    );
    expect(isRippleArtifact({ ...clone(), options: { ...OPTIONS, band_low_hz: -1 } })).toBe(false);
  });
});

describe("isRippleArtifact: инварианты доступности", () => {
  it("отбрасывает доступный блок с null-метрикой", () => {
    const fabricated = clone();
    fabricated.time_domain.mean_v = null;
    expect(isRippleArtifact(fabricated)).toBe(false);
  });

  it("отбрасывает недоступный блок с fabricated числом", () => {
    const fabricated = clone();
    fabricated.time_domain.availability = "unavailable";
    fabricated.time_domain.reason_codes = ["settling_unknown"];
    fabricated.time_domain.mean_v = 0.5;
    expect(isRippleArtifact(fabricated)).toBe(false);
  });

  it("отбрасывает недоступный блок без кодов причин", () => {
    const silent: RippleTimeDomain = {
      availability: "unavailable",
      reason_codes: [],
      mean_v: null,
      rms_ac_v: null,
      vpp_v: null,
    };
    expect(isRippleArtifact({ ...clone(), time_domain: silent })).toBe(false);
  });

  it("отбрасывает доступный блок с кодами причин", () => {
    const noisy = clone();
    noisy.time_domain.reason_codes = ["clipped"];
    expect(isRippleArtifact(noisy)).toBe(false);
  });

  it("отбрасывает недоступный интервал с числами и доступный с чужим типом", () => {
    expect(
      isRippleArtifact({
        ...clone(),
        intervals: [
          {
            ...INTERVAL_COMPLETE,
            availability: "unavailable",
            reason_codes: ["clipped"],
            vpp_v: 0.1,
          },
        ],
      }),
    ).toBe(false);
    expect(
      isRippleArtifact({
        ...clone(),
        intervals: [withString(INTERVAL_COMPLETE, "mean_v", "0.00002")],
      }),
    ).toBe(false);
  });

  it("отбрасывает интервал с рассинхроном исходных границ", () => {
    expect(
      isRippleArtifact({ ...clone(), intervals: [{ ...INTERVAL_COMPLETE, sample_count: 9_999 }] }),
    ).toBe(false);
    expect(
      isRippleArtifact({
        ...clone(),
        intervals: [{ ...INTERVAL_COMPLETE, end_index_exclusive: 10_000 }],
      }),
    ).toBe(false);
  });
});

describe("isRippleArtifact: спектр и серии", () => {
  it("отбрасывает серии разной длины и не-возрастающую сетку", () => {
    const ragged = clone();
    ragged.spectrum.psd_v2_per_hz = [1e-10, 2e-10];
    expect(isRippleArtifact(ragged)).toBe(false);
    const unsorted = clone();
    unsorted.spectrum.frequency_hz = [0, 2, 1];
    expect(isRippleArtifact(unsorted)).toBe(false);
  });

  it("отбрасывает отрицательную PSD и доступный спектр без точек", () => {
    const negative = clone();
    negative.spectrum.psd_v2_per_hz = [1e-10, -5e-10, 3e-10];
    expect(isRippleArtifact(negative)).toBe(false);
    const empty = clone();
    empty.spectrum.frequency_hz = [];
    empty.spectrum.psd_v2_per_hz = [];
    empty.spectrum.asd_v_per_sqrt_hz = [];
    expect(isRippleArtifact(empty)).toBe(false);
  });

  it("принимает нулевую PSD как конечное значение", () => {
    const zeros = clone();
    zeros.spectrum.psd_v2_per_hz = [0, 0, 0];
    zeros.spectrum.asd_v_per_sqrt_hz = [0, 0, 0];
    expect(isRippleArtifact(zeros)).toBe(true);
  });

  it("отбрасывает недоступный спектр с ненулевыми сериями и счётчиками", () => {
    const fabricated: RippleSpectrum = {
      availability: "unavailable",
      reason_codes: ["settling_unknown"],
      settings: {},
      used_sample_count: 30_000,
      ignored_tail_samples: 0,
      frequency_hz: [0],
      psd_v2_per_hz: [1e-10],
      asd_v_per_sqrt_hz: [1e-5],
    };
    expect(isRippleArtifact({ ...clone(), spectrum: fabricated })).toBe(false);
  });

  it("отбрасывает чужие типы в настройках Welch", () => {
    expect(
      isRippleArtifact({
        ...clone(),
        spectrum: { ...SPECTRUM, settings: { ...SPECTRUM.settings, segment_count: "5" } },
      }),
    ).toBe(false);
    expect(isRippleArtifact({ ...clone(), spectrum: omitKey(SPECTRUM, "settings") })).toBe(false);
    expect(
      isRippleArtifact({
        ...clone(),
        spectrum: { ...SPECTRUM, settings: { ...SPECTRUM.settings, nperseg: 1 } },
      }),
    ).toBe(false);
  });
});

describe("isRippleArtifact: хранимые полосы", () => {
  it("отбрасывает доступную полосу с null-числами и нулевыми бинами", () => {
    expect(isRippleArtifact({ ...clone(), bands: [{ ...BAND, rms_v: null }] })).toBe(false);
    expect(isRippleArtifact({ ...clone(), bands: [{ ...BAND, bin_count: 0 }] })).toBe(false);
  });

  it("отбрасывает недоступную полосу с числами и пустой список полос", () => {
    expect(
      isRippleArtifact({
        ...clone(),
        bands: [{ ...BAND, availability: "unavailable", bin_count: 500 }],
      }),
    ).toBe(false);
    expect(isRippleArtifact({ ...clone(), bands: [] })).toBe(false);
  });

  it("отбрасывает центры бинов вне запрошенной полосы", () => {
    expect(isRippleArtifact({ ...clone(), bands: [{ ...BAND, first_center_hz: 0.5 }] })).toBe(
      false,
    );
    expect(isRippleArtifact({ ...clone(), bands: [{ ...BAND, last_center_hz: 600 }] })).toBe(false);
    expect(isRippleArtifact({ ...clone(), bands: [{ ...BAND, first_center_hz: 0 }] })).toBe(false);
    // Инверсия порядка центров: last < first — не сетка частот.
    expect(isRippleArtifact({ ...clone(), bands: [{ ...BAND, last_center_hz: 0.5 }] })).toBe(false);
  });

  it("принимает полосу из одного бина: центры совпадают и лежат в границах", () => {
    // Узкая запрошенная полоса при шаге 1 Гц: маска выбирает один центр.
    const singleBin = {
      ...BAND,
      low_hz: 1,
      high_hz: 1.5,
      first_center_hz: 1,
      last_center_hz: 1,
      bin_count: 1,
    };
    expect(isRippleArtifact({ ...clone(), bands: [singleBin] })).toBe(true);
  });
});

describe("isRippleArtifact: границы спана и QC", () => {
  it("отбрасывает рассинхрон счётчиков спана", () => {
    expect(
      isRippleArtifact({ ...clone(), selection: { ...SELECTION, sample_count: 29_999 } }),
    ).toBe(false);
    expect(
      isRippleArtifact({
        ...clone(),
        selection: { ...SELECTION, sample_end_index_exclusive: 9_999 },
      }),
    ).toBe(false);
  });

  it("принимает пустой спан: границы равны, ветки недоступны, интервалов нет", () => {
    const artifact = clone();
    artifact.selection = {
      ...SELECTION,
      sample_end_index_exclusive: 10_000,
      sample_count: 0,
      realized_duration_s: 0,
    };
    artifact.intervals = [];
    artifact.time_domain = {
      availability: "unavailable",
      reason_codes: ["empty_span"],
      mean_v: null,
      rms_ac_v: null,
      vpp_v: null,
    };
    artifact.spectrum = {
      ...SPECTRUM_UNAVAILABLE,
      reason_codes: ["empty_span", "insufficient_samples"],
    };
    artifact.bands = [
      { ...BAND_UNAVAILABLE, reason_codes: ["empty_span", "insufficient_samples"] },
    ];
    expect(isRippleArtifact(artifact)).toBe(true);
  });

  it("отбрасывает рассинхрон счётчика спана с исходными границами", () => {
    expect(
      isRippleArtifact({
        ...clone(),
        selection: { ...SELECTION, sample_end_index_exclusive: 10_000, sample_count: 5 },
      }),
    ).toBe(false);
  });

  it("отбрасывает чужие статусы QC и дробные счётчики", () => {
    expect(
      isRippleArtifact({ ...clone(), qc: { ...QC, clipping_assessment: "maybe_clipped" } }),
    ).toBe(false);
    const fractional = clone();
    fractional.qc.nonfinite_count = 1.5;
    expect(isRippleArtifact(fractional)).toBe(false);
    expect(isRippleArtifact({ ...clone(), qc: { ...QC, clip_count_scope: "whole_record" } })).toBe(
      false,
    );
    expect(isRippleArtifact({ ...clone(), qc: { ...QC, clip_low_count: -1 } })).toBe(false);
    expect(isRippleArtifact({ ...clone(), qc: { ...QC, nonfinite_count_scope: "record" } })).toBe(
      false,
    );
  });
});

describe("isRippleArtifact: блок фона", () => {
  it("отбрасывает битую идентичность фона и чужую базу подключения", () => {
    const brokenIdentity: RippleBaseline = {
      session: { ...SESSION, session_id: "bg", manifest_sha256: "nothex" },
      attachment_basis: null,
      comparison_status: "unavailable",
      reason_codes: ["baseline_attachment_unqualified"],
      selection: null,
      time_domain: TIME_DOMAIN,
      spectrum: SPECTRUM,
      bands: [BAND],
    };
    expect(isRippleArtifact({ ...clone(), baseline: brokenIdentity })).toBe(false);
    const wrongAttachment = {
      ...brokenIdentity,
      session: SESSION,
      attachment_basis: "fifty_ohm_bnc",
    };
    expect(isRippleArtifact({ ...clone(), baseline: wrongAttachment })).toBe(false);
  });

  it("отбрасывает доступное сравнение с кодами причин и обратное", () => {
    const noisyAvailable = {
      session: SESSION,
      attachment_basis: "same_adapter_tip_shorted_to_return",
      comparison_status: "available",
      reason_codes: ["baseline_duration_mismatch"],
      selection: null,
      time_domain: TIME_DOMAIN,
      spectrum: SPECTRUM,
      bands: [BAND],
    };
    expect(isRippleArtifact({ ...clone(), baseline: noisyAvailable })).toBe(false);
    const silentUnavailable = {
      ...noisyAvailable,
      comparison_status: "unavailable",
      reason_codes: [],
    };
    expect(isRippleArtifact({ ...clone(), baseline: silentUnavailable })).toBe(false);
  });

  it("принимает фон с собственной идентичностью и доступными числами рядом", () => {
    const matched: RippleBaseline = {
      session: { ...SESSION, session_id: "syn-quiet-seed6024", ch1_sha256: hex64("b") },
      attachment_basis: "same_adapter_tip_shorted_to_return",
      comparison_status: "available",
      reason_codes: [],
      selection: SELECTION,
      time_domain: TIME_DOMAIN,
      spectrum: SPECTRUM,
      bands: [BAND],
    };
    expect(isRippleArtifact({ ...clone(), baseline: matched })).toBe(true);
  });
});
