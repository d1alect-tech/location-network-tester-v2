/** Guards spectrum-payloads: RBW ADD-ключи scope-спектра и input-referred контракт. */

import { describe, expect, it } from "vitest";
import { isInputReferredSpectrumPayload, isSpectrumPayload } from "./guards-plots";

const REFERRED = {
  frequency_hz: [10, 100, 1000],
  input_referred_excess_psd_v2_per_hz: [1e-12, 1e-10, 1e-11],
  point_count: 3,
  status: "available",
  reason_code: null,
  qualified_bin_count: 3,
  total_bin_count: 3,
  resolution_hz: 100,
};

describe("isSpectrumPayload: RBW ADD-ключи", () => {
  it("принимает scope-спектр с resolution_hz и полосой", () => {
    expect(
      isSpectrumPayload({
        frequency_hz: [10],
        psd_v2_per_hz: [1e-6],
        point_count: 1,
        resolution_hz: 97.65625,
        band_low_hz: 3000,
        band_high_hz: 1350000,
      }),
    ).toBe(true);
  });

  it("принимает старый payload без RBW-ключей", () => {
    expect(isSpectrumPayload({ frequency_hz: [10], psd_v2_per_hz: [1e-6], point_count: 1 })).toBe(
      true,
    );
  });

  it("отвергает нечисловой resolution_hz", () => {
    expect(
      isSpectrumPayload({
        frequency_hz: [10],
        psd_v2_per_hz: [1e-6],
        point_count: 1,
        resolution_hz: "100 Гц",
      }),
    ).toBe(false);
  });
});

describe("isInputReferredSpectrumPayload", () => {
  it("принимает полный контракт бэкенда", () => {
    expect(isInputReferredSpectrumPayload(REFERRED)).toBe(true);
  });

  it("принимает null resolution_hz/status (метаданных нет)", () => {
    expect(isInputReferredSpectrumPayload({ ...REFERRED, resolution_hz: null, status: null })).toBe(
      true,
    );
  });

  it("отвергает scope-ключ psd и неполный набор", () => {
    expect(
      isInputReferredSpectrumPayload({
        frequency_hz: [10],
        psd_v2_per_hz: [1e-6],
        point_count: 1,
      }),
    ).toBe(false);
    const { input_referred_excess_psd_v2_per_hz: _dropped, ...broken } = REFERRED;
    expect(isInputReferredSpectrumPayload(broken)).toBe(false);
  });
});
