import { describe, expect, it } from "vitest";
import type { SpectrumPayload } from "../../api/types-plots";
import { CHANNELBAR_DASH, createChannelbar } from "../../components/channelbar/channelbar";
import type { Meter } from "./analysisBand";
import { cyclesFromMeters, paintChannelbarFromPayload } from "./channelbarPaint";

const PAYLOAD: SpectrumPayload = {
  frequency_hz: [3000, 45000],
  psd_v2_per_hz: [1e-6, 1e-4],
  point_count: 2,
  resolution_hz: 30,
  band_low_hz: 3000,
  band_high_hz: 45000,
  window: "hann",
  enbw_hz: 45,
};

const METERS: Meter[] = [
  { label: "Циклов", value: "120" },
  { label: "Полоса", value: "3–45", unit: "кГц" },
];

describe("paintChannelbarFromPayload", () => {
  it("заливает пять полей из пейлоада и счётчиков", () => {
    const bar = createChannelbar();
    paintChannelbarFromPayload(bar, PAYLOAD, cyclesFromMeters(METERS));
    expect(bar.root.querySelector('[data-chbar="band"]')?.textContent).toBe("3 кГц – 45 кГц");
    expect(bar.root.querySelector('[data-chbar="rbw"]')?.textContent).toBe("45 Гц");
    expect(bar.root.querySelector('[data-chbar="window"]')?.textContent).toBe("Ханн");
    expect(bar.root.querySelector('[data-chbar="detector"]')?.textContent).toBe("Среднее");
    expect(bar.root.querySelector('[data-chbar="segments"]')?.textContent).toBe("120");
  });

  it("null-пейлоад гасит всё в прочерки", () => {
    const bar = createChannelbar();
    paintChannelbarFromPayload(bar, PAYLOAD, "120");
    paintChannelbarFromPayload(bar, null, null);
    for (const field of ["band", "rbw", "window", "detector", "segments"]) {
      expect(bar.root.querySelector(`[data-chbar="${field}"]`)?.textContent).toBe(CHANNELBAR_DASH);
    }
  });
});

describe("cyclesFromMeters", () => {
  it("берёт значение метра Циклов, отсутствие — в null", () => {
    expect(cyclesFromMeters(METERS)).toBe("120");
    expect(cyclesFromMeters([])).toBeNull();
  });
});
