/** Контракт-примеры guards-live: зеркала models_live.py — статус (state+mode),
 * триггер, кадр и событие ripple (models_ripple_live.py); некорректные
 * формы отбрасываются без исключений. */

import { describe, expect, it } from "vitest";
import {
  isLiveFramePayload,
  isLiveRipplePayload,
  isLiveSaConfig,
  isLiveSpectrumPayload,
  isLiveStatePayload,
  isLiveTrigger,
} from "./guards-live";

const TRIGGER = {
  level_v: 0.5,
  slope: "rising",
  source: "ch2",
  mode: "normal",
  auto_timeout_s: 0.2,
};

describe("isLiveTrigger", () => {
  it("accepts the wire mirror of TriggerConfig", () => {
    expect(isLiveTrigger(TRIGGER)).toBe(true);
  });

  it("rejects unknown enum values and non-numbers", () => {
    expect(isLiveTrigger({ ...TRIGGER, slope: "both" })).toBe(false);
    expect(isLiveTrigger({ ...TRIGGER, mode: "burst" })).toBe(false);
    expect(isLiveTrigger({ ...TRIGGER, level_v: "0" })).toBe(false);
    expect(isLiveTrigger(null)).toBe(false);
  });
});

describe("isLiveStatePayload", () => {
  it("accepts both states and modes with optional trigger", () => {
    expect(
      isLiveStatePayload({ state: "idle", mode: "sim", busy_reason: null, trigger: null }),
    ).toBe(true);
    expect(
      isLiveStatePayload({
        state: "running",
        mode: "real",
        busy_reason: "занято",
        trigger: TRIGGER,
      }),
    ).toBe(true);
    expect(
      isLiveStatePayload({ state: "stopped", mode: "sim", busy_reason: null, trigger: TRIGGER }),
    ).toBe(true);
  });

  it("rejects unknown state/mode and bad trigger", () => {
    expect(
      isLiveStatePayload({ state: "paused", mode: "sim", busy_reason: null, trigger: null }),
    ).toBe(false);
    expect(
      isLiveStatePayload({ state: "idle", mode: "fake", busy_reason: null, trigger: null }),
    ).toBe(false);
    expect(
      isLiveStatePayload({
        state: "idle",
        mode: "sim",
        busy_reason: null,
        trigger: { slope: "x" },
      }),
    ).toBe(false);
  });
});

describe("isLiveSaConfig", () => {
  it("accepts the wire mirror of SaConfig", () => {
    expect(
      isLiveSaConfig({
        rbw_hz: 50,
        window: "hann",
        band_low_hz: 0,
        band_high_hz: 4_000_000,
        detector: "mean",
      }),
    ).toBe(true);
    expect(
      isLiveSaConfig({
        rbw_hz: 300,
        window: "rect",
        band_low_hz: 1,
        band_high_hz: 2,
        detector: "min-hold",
      }),
    ).toBe(true);
  });

  it("rejects unknown window/detector and non-number fields", () => {
    expect(
      isLiveSaConfig({
        rbw_hz: 50,
        window: "bogus",
        band_low_hz: 0,
        band_high_hz: 1,
        detector: "mean",
      }),
    ).toBe(false);
    expect(
      isLiveSaConfig({
        rbw_hz: 50,
        window: "hann",
        band_low_hz: 0,
        band_high_hz: 1,
        detector: "avg",
      }),
    ).toBe(false);
    expect(
      isLiveSaConfig({
        rbw_hz: "50",
        window: "hann",
        band_low_hz: 0,
        band_high_hz: 1,
        detector: "mean",
      }),
    ).toBe(false);
    expect(isLiveSaConfig(null)).toBe(false);
  });
});

describe("isLiveSpectrumPayload", () => {
  const SPECTRUM = {
    frame_index: 3,
    freq: [100, 200, 300],
    psd_db: [-40, -30, -20],
    peaks: [
      { frequency_hz: 10_000, level_db: -30, prominence_db: 45, q_factor: null },
      { frequency_hz: 20_000, level_db: -50, prominence_db: 5, q_factor: 2.5 },
    ],
    meta: { enbw: 75, resolution: 125, window: "hann", rbw: 50 },
  };

  it("accepts a full sweep with peaks and meta", () => {
    expect(isLiveSpectrumPayload(SPECTRUM)).toBe(true);
    expect(isLiveSpectrumPayload({ ...SPECTRUM, peaks: [] })).toBe(true);
  });

  it("rejects ragged series, empty grid, bad peaks and bad meta", () => {
    expect(isLiveSpectrumPayload({ ...SPECTRUM, psd_db: [-40, -30] })).toBe(false);
    expect(isLiveSpectrumPayload({ ...SPECTRUM, freq: [], psd_db: [] })).toBe(false);
    expect(
      isLiveSpectrumPayload({ ...SPECTRUM, peaks: [{ frequency_hz: 1, level_db: "x" }] }),
    ).toBe(false);
    expect(
      isLiveSpectrumPayload({
        ...SPECTRUM,
        meta: { enbw: 75, resolution: 125, window: 5, rbw: 50 },
      }),
    ).toBe(false);
    expect(isLiveSpectrumPayload("spectrum")).toBe(false);
  });
});

describe("isLiveFramePayload", () => {
  const FRAME = {
    frame_index: 12,
    triggered: false,
    emitted_at_s: 0.4,
    dropped_samples: 3,
    skipped_frames: 1,
    sample_rate_hz: 8_000_000,
    frame_samples: 4096,
    decimated: true,
    calibration_used: false,
    ch1: { time_s: [0, 0.001], voltage_v: [0, 1], point_count: 2 },
    ch2: { time_s: [0, 0.001], voltage_v: [0, -1], point_count: 2 },
  };

  it("accepts a full frame with both channel series", () => {
    expect(isLiveFramePayload(FRAME)).toBe(true);
  });

  it("rejects missing ch2, non-boolean flags and string voltage", () => {
    const { ch2: _ch2, ...withoutCh2 } = FRAME;
    void _ch2;
    expect(isLiveFramePayload(withoutCh2)).toBe(false);
    expect(isLiveFramePayload({ ...FRAME, triggered: "yes" })).toBe(false);
    expect(isLiveFramePayload({ ...FRAME, ch1: { ...FRAME.ch1, voltage_v: ["0"] } })).toBe(false);
    expect(isLiveFramePayload("frame")).toBe(false);
  });
});

describe("isLiveRipplePayload", () => {
  const ADAPTER = {
    topology_id: "series_c_at_dut_tip_x1_v1",
    cap_nf: 100,
    series_r_ohm: 0,
    probe_multiplier: 1,
    component_values_basis: "nominal",
    hardware_qualification: "unverified",
    transfer_status: "nominal_transfer_declared",
    rail_nominal_v: null,
    tau_s: 0.1,
    fc_hz: 1.5915,
    settling_s: 1,
    settle_samples: 8000,
    assumption_codes: ["one_pole_nominal_transfer"],
  };
  const BASE = {
    status: "settling",
    reason_codes: ["settling_window"],
    epoch_id: 1,
    config_id: "cfg1",
    continuity_id: 1,
    continuity_basis: "host_contiguous_unverified",
    gap_count: 0,
    block_count: 3,
    dropped_blocks: 0,
    dropped_samples: 0,
    samples_received: 1000,
    sample_progress: 1000,
    ring_capacity_samples: 524_288,
    ring_sample_count: 1000,
    ring_limited: false,
    settle_samples: 8000,
    settled: false,
    startup_discard_samples: 0,
    settling_basis: "capture_start_assuming_preconnected",
    settling_remaining_samples: 7000,
    excluded_prefix_samples: 8000,
    span_start_sample: null,
    span_sample_count: 0,
    span_duration_s: null,
    mean_v: null,
    rms_ac_v: null,
    vpp_v: null,
    clipped_low: 0,
    clipped_high: 0,
    clip_count_scope: "current_span",
    sample_rate_hz: 8000,
    ch1_range_v: 5,
    ch1_probe_multiplier: 1,
    calibration_used: false,
    voltage_label: "некалиброванные вольты",
    adapter: ADAPTER,
  };
  const READY = {
    ...BASE,
    status: "ready",
    settled: true,
    settling_remaining_samples: 0,
    span_start_sample: 8000,
    span_sample_count: 4000,
    span_duration_s: 0.5,
    mean_v: 0.0012,
    rms_ac_v: 0.0354,
    vpp_v: 0.1,
  };

  it("принимает settling (числа null) и ready (числа конечны)", () => {
    expect(isLiveRipplePayload(BASE)).toBe(true);
    expect(isLiveRipplePayload(READY)).toBe(true);
    expect(isLiveRipplePayload({ ...BASE, continuity_basis: "synthetic_exact" })).toBe(true);
  });

  it("инвариант статуса: числа ровно у ready, иначе все три null", () => {
    expect(isLiveRipplePayload({ ...BASE, status: "ready" })).toBe(false);
    expect(isLiveRipplePayload({ ...READY, status: "stopped" })).toBe(false);
    expect(isLiveRipplePayload({ ...READY, rms_ac_v: null })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, mean_v: 0.001 })).toBe(false);
  });

  it("отбрасывает NaN/Infinity, нулевую частоту и нецелые счётчики", () => {
    expect(isLiveRipplePayload({ ...READY, rms_ac_v: Number.NaN })).toBe(false);
    expect(isLiveRipplePayload({ ...READY, vpp_v: Number.POSITIVE_INFINITY })).toBe(false);
    expect(isLiveRipplePayload({ ...READY, sample_rate_hz: 0 })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, epoch_id: 1.5 })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, dropped_samples: -1 })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, settling_remaining_samples: -3 })).toBe(false);
  });

  it("отбрасывает чужие enum-значения, ярлык и битый адаптер", () => {
    expect(isLiveRipplePayload({ ...BASE, status: "paused" })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, continuity_basis: "hardware" })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, settling_basis: "connection_observed" })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, voltage_label: "вольты" })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, clip_count_scope: "whole_record" })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, reason_codes: "settling_window" })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, ring_limited: "no" })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, adapter: { ...ADAPTER, cap_nf: Number.NaN } })).toBe(
      false,
    );
    expect(isLiveRipplePayload({ ...BASE, adapter: { topology_id: "x" } })).toBe(false);
    expect(isLiveRipplePayload({ ...BASE, settle_samples: "8000" })).toBe(false);
    expect(isLiveRipplePayload("ripple")).toBe(false);
    expect(isLiveRipplePayload(null)).toBe(false);
  });
});
