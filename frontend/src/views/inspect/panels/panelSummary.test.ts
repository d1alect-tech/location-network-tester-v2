import { describe, expect, it } from "vitest";
import { panelKeyText } from "./panelSummary";

/** Given / When / Then: ключевое значение свёрнутой шапки — факт из парсера,
 * а не вторая математика; нет данных — null, никогда не «0». */

const HARMONICS = {
  windows: [
    { index: 0, start_time_s: 0, thd: 0.04, fundamental_rms: 230 },
    { index: 1, start_time_s: 0.02, thd: 0.06, fundamental_rms: 228 },
  ],
};

describe("panelKeyText", () => {
  it("reads the mean THD of the harmonics windows", () => {
    // Given / When / Then: (0.04 + 0.06) / 2 = 0.05, формат w1Parse.formatScalar
    expect(panelKeyText("harmonics", HARMONICS)).toBe("THD 0.05000");
  });

  it("reads the deepest notch in volts", () => {
    // Given
    const payload = {
      notches: [
        { start_time_s: 0, end_time_s: 1, depth_v: 0.2, duration_us: 10, area_v_us: 2 },
        { start_time_s: 1, end_time_s: 2, depth_v: 0.75, duration_us: 10, area_v_us: 7 },
      ],
    };

    // When / Then
    expect(panelKeyText("notching", payload)).toBe("пик 0.7500 В");
  });

  it("prefers the APD slope and falls back to the bin count", () => {
    // Given
    const bins = { apd: [{ amplitude_v: 0.1, exceedance_prob: 0.5, level_db: -20 }] };

    // When / Then
    expect(panelKeyText("apd", { ...bins, apd_slope_db_per_decade: -20.5 })).toBe(
      "slope -20.50 dB/dec",
    );
    expect(panelKeyText("apd", bins)).toBe("1 бинов");
  });

  it("keeps burst_count 0 as a real count", () => {
    expect(panelKeyText("burst", { burst_count: 0, bursts: [] })).toBe("0");
    expect(panelKeyText("burst", { burst_count: 7, bursts: [] })).toBe("7");
  });

  it("reads crest factor, audio band RMS and CM/DM bins", () => {
    // Given
    const trends = {
      crest_factor: 1.5,
      rms_v: 0.2,
      peak_v: 0.283,
      theil_sen_slope: 0,
      theil_sen_intercept: 0.2,
      discard_samples: 8,
      eeprom_verified: true,
      change_points: [],
    };
    const audio = { low_hz: 20, high_hz: 3000, band_rms_v: 0.0125, peaks: [] };
    const csv = "frequency_hz,cm_psd,dm_psd,coherence\n1000,1e-6,2e-6,0.5\n2000,1e-6,2e-6,0.5\n";

    // When / Then
    expect(panelKeyText("trends", trends)).toBe("crest 1.500");
    expect(panelKeyText("audio", audio)).toBe("band_rms 0.01250 V");
    expect(panelKeyText("cm_dm", csv)).toBe("бинов: 2");
  });

  it("counts SEMI-F47 verdicts for ITIC", () => {
    // Given: одно событие вне кривой → unavailable, событий больше нуля.
    const payload = {
      half_cycle_rms_summary: { count: 240, min: 200, max: 240, nominal_rms_v: 230 },
      events: [{ kind: "dip" }],
      rvc_events: [],
    };

    // When / Then
    expect(panelKeyText("itic", payload)).toBe("SEMI-F47 N/A (1)");
  });

  it("returns null instead of a fake 0 for missing or unparsable payloads", () => {
    // Given / When / Then
    expect(panelKeyText("harmonics", null)).toBeNull();
    expect(panelKeyText("harmonics", { windows: [] })).toBeNull();
    expect(panelKeyText("notching", {})).toBeNull();
    expect(panelKeyText("apd", { apd: [] })).toBeNull();
    expect(panelKeyText("burst", null)).toBeNull();
    expect(panelKeyText("trends", { crest_factor: 1.2 })).toBeNull();
    expect(panelKeyText("audio", { peaks: [] })).toBeNull();
    expect(panelKeyText("itic", { events: [] })).toBeNull();
    expect(panelKeyText("cm_dm", "")).toBeNull();
    expect(panelKeyText("cm_dm", 42)).toBeNull();
    expect(panelKeyText("branch-failure", {})).toBeNull();
  });
});
