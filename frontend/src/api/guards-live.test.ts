/** Контракт-примеры guards-live: зеркала models_live.py — статус (state+mode),
 * триггер и кадр; некорректные формы отбрасываются без исключений. */

import { describe, expect, it } from "vitest";
import {
  isLiveFramePayload,
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
