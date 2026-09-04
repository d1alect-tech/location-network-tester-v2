import { describe, expect, it } from "vitest";
import type { SessionDetailPayload } from "../../api/types-plots";
import {
  createAnalysisBand,
  metersFromDetail,
  type Meter,
  type PeakRow,
} from "./analysisBand";

const METER_LABELS = [
  "Частота сети",
  "μ иглы",
  "σ/μ",
  "P_async/P_sync",
  "Циклов",
  "Полоса",
  "Разрешение",
] as const;

function sessionDetail(analysis: Record<string, unknown> | null): SessionDetailPayload {
  return {
    name: "ses-a",
    manifest: {},
    analysis,
    spectrum_available: true,
    waveform_available: true,
    ch2_available: analysis !== null,
  };
}

const FULL_ANALYSIS = {
  needle: {
    line_frequency_hz: 50.0000007,
    needle_mean_v: 1.2904717,
    needle_sigma_ratio: 6.217754,
    async_sync_ratio: 73.286217,
    cycles_analyzed: 118,
  },
  spectrum: {
    band_low_hz: 3000,
    band_high_hz: 45000,
    resolution_hz: 97.65625,
  },
} as const;

const CHANNEL1_ANALYSIS = {
  needle: {
    line_frequency_hz: null,
    needle_mean_v: 1.2904717,
    needle_sigma_ratio: null,
    async_sync_ratio: null,
    cycles_analyzed: 118,
  },
  spectrum: {
    band_low_hz: 3000,
    band_high_hz: 45000,
    resolution_hz: 97.65625,
  },
} as const;

function meterByLabel(meters: readonly Meter[], label: string): Meter | undefined {
  return meters.find((meter) => meter.label === label);
}

describe("metersFromDetail", () => {
  it("returns 7 readout meters with expected labels from a full session-A detail", () => {
    // Given
    const detail = sessionDetail({ ...FULL_ANALYSIS });

    // When
    const meters = metersFromDetail(detail);

    // Then
    expect(meters).toHaveLength(7);
    expect(meters.map((meter) => meter.label)).toEqual([...METER_LABELS]);
    expect(meterByLabel(meters, "Частота сети")).toEqual({
      label: "Частота сети",
      value: "50.0000007",
      unit: "Гц",
    });
    expect(meterByLabel(meters, "μ иглы")).toEqual({
      label: "μ иглы",
      value: "1.2905",
      unit: "В",
    });
    expect(meterByLabel(meters, "σ/μ")?.value).toBe("6.218");
    expect(meterByLabel(meters, "P_async/P_sync")?.value).toBe("73.29");
    expect(meterByLabel(meters, "Циклов")?.value).toBe("118");
    const ru = new Intl.NumberFormat("ru-RU");
    expect(meterByLabel(meters, "Полоса")).toEqual({
      label: "Полоса",
      value: `${ru.format(3000)}–${ru.format(45000)}`,
      unit: "Гц",
    });
    expect(meterByLabel(meters, "Разрешение")).toEqual({
      label: "Разрешение",
      value: "97.65625",
      unit: "Гц",
    });
  });

  it("returns н/д for null async and sigma on a 1-channel detail, never 0 or NaN", () => {
    // Given
    const detail = sessionDetail({ ...CHANNEL1_ANALYSIS });

    // When
    const meters = metersFromDetail(detail);

    // Then
    expect(meters).toHaveLength(7);
    const sigma = meterByLabel(meters, "σ/μ");
    const asyncSync = meterByLabel(meters, "P_async/P_sync");
    const lineHz = meterByLabel(meters, "Частота сети");
    expect(sigma?.value).toBe("н/д");
    expect(asyncSync?.value).toBe("н/д");
    expect(lineHz?.value).toBe("н/д");
    for (const meter of [sigma, asyncSync, lineHz]) {
      expect(meter?.value).not.toBe("0");
      expect(meter?.value).not.toBe("NaN");
      expect(meter?.value).not.toMatch(/NaN/);
    }
  });
});

describe("createAnalysisBand", () => {
  const sampleMeters: readonly Meter[] = [
    { label: "Частота сети", value: "50.0000007", unit: "Гц" },
    { label: "μ иглы", value: "1.2905", unit: "В" },
    { label: "σ/μ", value: "6.218" },
    { label: "P_async/P_sync", value: "73.29" },
    { label: "Циклов", value: "118" },
    { label: "Полоса", value: "3 000–45 000", unit: "Гц" },
    { label: "Разрешение", value: "97.65625", unit: "Гц" },
  ];

  const samplePeaks: readonly PeakRow[] = [
    {
      frequencyHz: 22418.2,
      baseDb: -48.57,
      deltaDb: -10,
      prominenceDb: 26.5,
      q: 8.92,
    },
    {
      frequencyHz: 27439.8,
      baseDb: -49.95,
      deltaDb: null,
      prominenceDb: 27.08,
      q: 10.95,
    },
  ];

  it("renders readout cells and peak rows on update", () => {
    // Given
    const band = createAnalysisBand();

    // When
    band.update({ meters: [...sampleMeters], peaks: [...samplePeaks] });

    // Then
    expect(band.root.classList.contains("analysis-band")).toBe(true);
    const readout = band.root.querySelector(".panel.readout");
    expect(readout).not.toBeNull();
    expect(readout?.querySelector(".panel-hd")?.textContent).toContain("Показания базы");
    const cells = band.root.querySelectorAll(".readout-grid .readout-cell");
    expect(cells).toHaveLength(7);
    expect(cells[0]?.querySelector(".readout-label")?.textContent).toBe("Частота сети");
    expect(cells[0]?.querySelector(".readout-value")?.textContent).toContain("50.0000007");
    expect(cells[0]?.querySelector(".t-unit")?.textContent).toBe("Гц");
    const wide = band.root.querySelector(".readout-cell.is-wide");
    expect(wide?.querySelector(".readout-label")?.textContent).toBe("Полоса");
    const peaksHd = band.root.querySelectorAll(".panel-hd");
    expect(peaksHd[1]?.textContent).toContain("Пики спектра · дельта к базе");
    const table = band.root.querySelector("table.tbl.tbl-compare");
    expect(table).not.toBeNull();
    const rows = table?.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(2);
    const firstCells = rows?.[0]?.querySelectorAll("td");
    expect(firstCells?.[0]?.classList.contains("num")).toBe(true);
    expect(firstCells?.[1]?.textContent).toBe("-48.57");
  });

  it("renders data-delta -10.00 and glyph ▼ when deltaDb is -10", () => {
    // Given
    const band = createAnalysisBand();
    const peak: PeakRow = {
      frequencyHz: 1000,
      baseDb: -40,
      deltaDb: -10,
      prominenceDb: 12,
      q: 4,
    };

    // When
    band.update({ meters: [], peaks: [peak] });

    // Then
    const delta = band.root.querySelector("td.delta");
    expect(delta?.getAttribute("data-delta")).toBe("-10.00");
    expect(delta?.classList.contains("is-down")).toBe(true);
    expect(delta?.querySelector(".delta-glyph")?.textContent).toBe("▼");
    expect(delta?.querySelector(".delta-glyph")?.getAttribute("aria-hidden")).toBe("true");
    expect(delta?.textContent).toContain("10.0");
  });

  it("renders em dash and no numeric data-delta when deltaDb is null", () => {
    // Given
    const band = createAnalysisBand();
    const peak: PeakRow = {
      frequencyHz: 1000,
      baseDb: -40,
      deltaDb: null,
      prominenceDb: 12,
      q: 4,
    };

    // When
    band.update({ meters: [], peaks: [peak] });

    // Then
    const delta = band.root.querySelector("td.delta");
    expect(delta?.classList.contains("is-flat")).toBe(true);
    expect(delta?.hasAttribute("data-delta")).toBe(false);
    expect(delta?.textContent).toBe("—");
  });
});
