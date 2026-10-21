/** RED-first контракт модели панели «Риппл / шум»: формат значений,
 * честные причины недоступности, выбор только ХРАНИМЫХ полос и спектра.
 * Числа в data-value — байты артефакта, не пересчёт панели. */

import { describe, expect, it } from "vitest";
import type {
  RippleArtifactPayload,
  RippleBaseline,
  RippleSpectrum,
  RippleTimeDomain,
} from "../../../api/types-ripple";
import { chartRequest } from "./rippleChart";
import { buildRippleView, formatVolts, reasonText } from "./rippleModel";

const hex64 = (char: string): string => char.repeat(64);

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

function fixture(): RippleArtifactPayload {
  const time_domain: RippleTimeDomain = {
    availability: "available",
    reason_codes: [],
    mean_v: 0.000005173322720890401,
    rms_ac_v: 0.002117531120011638,
    vpp_v: 0.021350678987801075,
  };
  return {
    schema_version: 1,
    algorithm: { id: "ripple_observed_v1", version: 1, rms: "population_centered_float64" },
    options: { band_low_hz: 1, band_high_hz: 500, interval_window_s: 1 },
    session: {
      session_id: "syn-quiet-seed6022",
      manifest_sha256: hex64("f"),
      ch1_sha256: hex64("e"),
      channel: "ch1",
      source: "synthetic",
    },
    provenance: {
      capture_metadata_basis: "legacy_capture_metadata_not_adapter_provenance",
      operator_attachment: "preconnected_no_reconnection",
      voltage_plane: "synthetic_mathematical_volts",
      range_code: 1,
      probe_multiplier: 1,
      calibration_used: null,
      calibration_identity: null,
      hardware_qualification: "unverified",
    },
    adapter: {
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
    },
    selection: {
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
    },
    qc: {
      clipping_assessment: "not_applicable_synthetic",
      clip_count_scope: null,
      clip_low_count: null,
      clip_high_count: null,
      nonfinite_count: 0,
      nonfinite_count_scope: "selected_span",
      record_nonfinite_count: 0,
      dropped_samples: 0,
      reason_codes: [],
    },
    time_domain,
    intervals: [
      {
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
      },
      {
        start_index: 20_000,
        end_index_exclusive: 30_000,
        sample_count: 10_000,
        complete: true,
        realized_duration_s: 1,
        availability: "available",
        reason_codes: [],
        clip_low_count: 0,
        clip_high_count: 0,
        mean_v: 0.00001,
        rms_ac_v: 0.0022,
        vpp_v: 0.021,
      },
      {
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
      },
    ],
    spectrum: SPECTRUM,
    bands: [
      {
        id: "ripple",
        low_hz: 1,
        high_hz: 500,
        first_center_hz: 1,
        last_center_hz: 500,
        bin_count: 500,
        availability: "available",
        reason_codes: [],
        rms_v: 0.0006369719075516393,
      },
    ],
    baseline: null,
  };
}

describe("formatVolts", () => {
  it("недоступное значение — «н/д», а не ноль", () => {
    expect(formatVolts(null)).toBe("н/д");
  });

  it("милливольты с запятой и неразрывным пробелом", () => {
    expect(formatVolts(0.03535533905932738)).toBe("35,36\u00A0мВ");
  });

  it("ровно ноль — измеренный ноль, не «н/д»", () => {
    expect(formatVolts(0)).toBe("0,00\u00A0мВ");
  });

  it("микровольты для малых значений", () => {
    expect(formatVolts(0.000005173322720890401)).toBe("5,17\u00A0мкВ");
  });

  it("длинное число не выходит за фиксированный слот (≤ 10 знаков)", () => {
    expect(formatVolts(-0.123456789)).toBe("-123,46\u00A0мВ");
    expect(formatVolts(-0.999999)).toBe("-1,000\u00A0В");
  });
});

describe("reasonText", () => {
  it("переводит известные машинные коды", () => {
    expect(reasonText("clipped")).toBe("клиппинг");
    expect(reasonText("insufficient_samples")).toBe("мало отсчётов");
    expect(reasonText("settling_unknown")).toBe("установление не подтверждено");
  });

  it("неизвестный код показывает дословно, а не выдумывает причину", () => {
    expect(reasonText("future_reason_v9")).toBe("future_reason_v9");
    expect(reasonText(null)).toBe("причина не указана");
  });
});

describe("buildRippleView", () => {
  it("метрики несут байты артефакта в raw и отформатированный текст", () => {
    const view = buildRippleView(fixture(), 0);
    expect(view.state).toBe("ready");
    expect(view.metrics.map((metric) => metric.key)).toEqual(["mean", "rms-ac", "vpp", "band"]);
    expect(view.metrics[0]?.raw).toBe(0.000005173322720890401);
    expect(view.metrics[1]?.raw).toBe(0.002117531120011638);
    expect(view.metrics[2]?.raw).toBe(0.021350678987801075);
    expect(view.metrics[3]?.raw).toBe(0.0006369719075516393);
    expect(view.metrics[1]?.text).toBe("2,12\u00A0мВ");
  });

  it("чипы честности: некалиброванные вольты, программная полоса, окно установления", () => {
    const view = buildRippleView(fixture(), 0);
    expect(view.chips).toContain("математические вольты (синтетика)");
    expect(view.chips).toContain("программная полоса 1–500\u00A0Гц");
    expect(view.chips).toContain("окно установления 1,000\u00A0с");
  });

  it("недоступная ветка — н/д с причиной, полоса остаётся своей", () => {
    const artifact = fixture();
    artifact.time_domain = {
      availability: "unavailable",
      reason_codes: ["clipping_unknown"],
      mean_v: null,
      rms_ac_v: null,
      vpp_v: null,
    };
    const view = buildRippleView(artifact, 0);
    expect(view.state).toBe("ready");
    expect(view.availability).toBe("unavailable");
    for (const key of ["mean", "rms-ac", "vpp"]) {
      const metric = view.metrics.find((item) => item.key === key);
      expect(metric?.raw).toBeNull();
      expect(metric?.text).toBe("н/д");
      expect(metric?.reason).toBe("клиппинг не определён");
    }
    expect(view.metrics[3]?.raw).toBe(0.0006369719075516393);
  });

  it("выбирает только хранимую полосу; индекс зажимается", () => {
    const artifact = fixture();
    artifact.bands.push({
      ...artifact.bands[0]!,
      id: "wide",
      low_hz: 10,
      high_hz: 2000,
      rms_v: 0.001,
    });
    expect(buildRippleView(artifact, 1).selectedBand).toBe(1);
    expect(buildRippleView(artifact, 1).metrics[3]?.raw).toBe(0.001);
    expect(buildRippleView(artifact, 99).selectedBand).toBe(1);
    expect(buildRippleView(artifact, -3).selectedBand).toBe(0);
    expect(buildRippleView(artifact, 0).bands).toHaveLength(2);
  });

  it("фон null — сравнение не выполнялось; фон рядом без вычитания", () => {
    const without = buildRippleView(fixture(), 0);
    expect(without.baseline.status).toBe("none");
    expect(without.baseline.rmsText).toBe("н/д");

    const baseline: RippleBaseline = {
      session: {
        session_id: "bg",
        manifest_sha256: hex64("a"),
        ch1_sha256: hex64("b"),
        channel: "ch1",
        source: "synthetic",
      },
      attachment_basis: "same_adapter_tip_shorted_to_return",
      comparison_status: "unavailable",
      reason_codes: ["baseline_incompatible"],
      selection: null,
      time_domain: {
        availability: "available",
        reason_codes: [],
        mean_v: 0,
        rms_ac_v: 0.001,
        vpp_v: 0.003,
      },
      spectrum: {
        availability: "unavailable",
        reason_codes: ["baseline_incompatible"],
        settings: {},
        used_sample_count: null,
        ignored_tail_samples: null,
        frequency_hz: [],
        psd_v2_per_hz: [],
        asd_v_per_sqrt_hz: [],
      },
      bands: [],
    };
    const artifact = fixture();
    artifact.baseline = baseline;
    const withBaseline = buildRippleView(artifact, 0);
    expect(withBaseline.baseline.status).toBe("unavailable");
    expect(withBaseline.baseline.rmsText).toBe("1,00\u00A0мВ");
    expect(withBaseline.baseline.text).toContain("сравнение");
    // Измерение не подменяется фоном и не вычитается.
    expect(withBaseline.metrics[1]?.raw).toBe(0.002117531120011638);
  });
});

describe("chartRequest", () => {
  it("PSD — 10·lg сохранённого PSD, нулевой бин отброшен", () => {
    const request = chartRequest(fixture(), "psd", "#5681ff");
    expect(request).not.toBeNull();
    expect(request?.x).toEqual([1, 2]);
    expect(request?.yLog).toBe(false);
    expect(request?.xLog).toBe(true);
    expect(request?.yLabel).toBe("дБ (1 В²/Гц)");
    expect(request?.series[0]?.values[0]).toBeCloseTo(10 * Math.log10(5.662041868960643e-10), 12);
  });

  it("ASD — сохранённый ASD на лог-оси, без пересчёта в панели", () => {
    const request = chartRequest(fixture(), "asd", "#5681ff");
    expect(request?.series[0]?.values).toEqual([2.379e-5, 1.898e-5]);
    expect(request?.yLog).toBe(true);
    expect(request?.yLabel).toBe("В/√Гц (лог)");
  });

  it("недоступный спектр не рисуется и не выдумывает точки", () => {
    const artifact = fixture();
    artifact.spectrum = {
      availability: "unavailable",
      reason_codes: ["insufficient_segments"],
      settings: {},
      used_sample_count: null,
      ignored_tail_samples: null,
      frequency_hz: [],
      psd_v2_per_hz: [],
      asd_v_per_sqrt_hz: [],
    };
    expect(chartRequest(artifact, "psd", "#5681ff")).toBeNull();
  });
});
