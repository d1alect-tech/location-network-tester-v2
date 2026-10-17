import { describe, expect, it } from "vitest";
import type { SessionDetailPayload } from "../../api/types-plots";
import { type Meter, type PeakRow, createAnalysisBand, metersFromDetail } from "./analysisBand";
import { REASON_NO_ARTIFACT, branchNotComputedReason } from "./pairLoadOutcome";

const REASON_BRANCH = branchNotComputedReason("");

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

  it("renders two rows: scalar tiles then peaks plus delta rail", () => {
    // Given
    const band = createAnalysisBand();

    // When
    band.update({ meters: [...sampleMeters], peaks: [...samplePeaks] });

    // Then
    expect(band.root.classList.contains("analysis-band")).toBe(true);
    expect(band.root.getAttribute("data-band-variant")).toBe("two-rows");
    expect(band.root.querySelector(".panel-hd")?.textContent).toContain("Показания базы");
    const cells = band.root.querySelectorAll(".band-scalars .band-cell");
    expect(cells).toHaveLength(7);
    expect(cells[0]?.querySelector("dt")?.textContent).toBe("Частота сети");
    expect(cells[0]?.querySelector("dd")?.textContent).toContain("50.0000007");
    expect(cells[0]?.querySelector(".t-unit")?.textContent).toBe("Гц");
    const wide = band.root.querySelector(".band-cell.is-wide");
    expect(wide?.querySelector("dt")?.textContent).toBe("Полоса");
    expect(wide?.querySelector("dd")?.classList.contains("is-long")).toBe(true);
    const peaksHd = band.root.querySelectorAll(".panel-hd");
    expect(peaksHd[1]?.textContent).toContain("Пики спектра · дельта к базе");
    const table = band.root.querySelector("table.tbl.tbl-compare");
    expect(table).not.toBeNull();
    const rows = table?.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(2);
    const firstCells = rows?.[0]?.querySelectorAll("td");
    expect(firstCells?.[0]?.classList.contains("num")).toBe(true);
    expect(firstCells?.[1]?.textContent).toBe("-48.57");
    // Δ-полоса живёт во втором ряду ленты, рядом с пиками.
    expect(band.root.querySelector(".band-tier2 .band-rail [data-delta-canvas]")).not.toBeNull();
    expect(band.root.querySelector(".band-rail-note")?.textContent).toContain("±8 дБ");
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

describe("metersFromDetail: причины «н/д» из честных флагов detail (задача 9)", () => {
  it("analysis:null → все значения «н/д» с причиной «нет артефакта»", () => {
    // Given
    const detail = sessionDetail(null);

    // When
    const meters = metersFromDetail(detail);

    // Then
    expect(meters).toHaveLength(7);
    for (const meter of meters) {
      expect(meter.value).toBe("н/д");
      expect(meter.reason).toBe(REASON_NO_ARTIFACT);
    }
  });

  it("metrics есть, spectrum.csv нет: полоса/разрешение «н/д» с причиной «нет артефакта»", () => {
    // Given — зеркало corpus-строки cap-20260805-212516: analysis без веток
    // needle/spectrum (фикстура числа не выдумывает), spectrum_available false.
    const detail: SessionDetailPayload = {
      name: "cap-20260805-212516",
      manifest: {},
      analysis: { session_id: "cap-20260805-212518-4e246d77", schema_version: 1 },
      spectrum_available: false,
      waveform_available: true,
      ch2_available: false,
    };

    // When
    const meters = metersFromDetail(detail);

    // Then
    expect(meterByLabel(meters, "Полоса")?.value).toBe("н/д");
    expect(meterByLabel(meters, "Полоса")?.reason).toBe(REASON_NO_ARTIFACT);
    expect(meterByLabel(meters, "Разрешение")?.value).toBe("н/д");
    expect(meterByLabel(meters, "Разрешение")?.reason).toBe(REASON_NO_ARTIFACT);
  });

  it("spectrum_available true, ветки спектра нет: «ветка не посчитана»", () => {
    // Given — metrics с иглой, но без ветки spectrum; spectrum.csv при этом есть.
    const detail: SessionDetailPayload = {
      name: "ses-spectrum-csv",
      manifest: {},
      analysis: { needle: { ...FULL_ANALYSIS.needle } },
      spectrum_available: true,
      waveform_available: true,
      ch2_available: false,
    };

    // When
    const meters = metersFromDetail(detail);

    // Then
    expect(meterByLabel(meters, "Полоса")?.value).toBe("н/д");
    expect(meterByLabel(meters, "Полоса")?.reason).toBe(REASON_BRANCH);
    expect(meterByLabel(meters, "Разрешение")?.reason).toBe(REASON_BRANCH);
    // Игла посчитана — причина не появляется.
    expect(meterByLabel(meters, "μ иглы")?.reason).toBeUndefined();
  });

  it("analysis без ветки needle: иглы «н/д» с причиной «ветка не посчитана»", () => {
    // Given
    const detail: SessionDetailPayload = {
      name: "qa-line-quality",
      manifest: {},
      analysis: { session_id: "qa-line-quality", schema_version: 1 },
      spectrum_available: false,
      waveform_available: true,
      ch2_available: false,
    };

    // When
    const meters = metersFromDetail(detail);

    // Then
    for (const label of ["Частота сети", "μ иглы", "σ/μ", "P_async/P_sync", "Циклов"]) {
      expect(meterByLabel(meters, label)?.value).toBe("н/д");
      expect(meterByLabel(meters, label)?.reason).toBe(REASON_BRANCH);
    }
  });

  it("null-поле существующей ветки: причина не выдумывается", () => {
    // Given — 1-канальная сессия: σ/μ и async null, ветка needle посчитана.
    const detail = sessionDetail({ ...CHANNEL1_ANALYSIS });

    // When
    const meters = metersFromDetail(detail);

    // Then
    expect(meterByLabel(meters, "σ/μ")?.value).toBe("н/д");
    expect(meterByLabel(meters, "σ/μ")?.reason).toBeUndefined();
    expect(meterByLabel(meters, "P_async/P_sync")?.reason).toBeUndefined();
    expect(meterByLabel(meters, "Полоса")?.reason).toBeUndefined();
  });

  it("полный анализ: значений причины нет — пин значений не тронут", () => {
    // Given
    const detail = sessionDetail({ ...FULL_ANALYSIS });

    // When
    const meters = metersFromDetail(detail);

    // Then
    expect(meters).toHaveLength(7);
    for (const meter of meters) expect(meter.reason).toBeUndefined();
  });
});

describe("createAnalysisBand: причина «н/д» — ВИДИМЫЙ соседний узел (задача 9, F-1)", () => {
  it("«н/д»-плитка: span.band-cell-reason ПОСЛЕ dd; текст dd байт-в-байт не тронут", () => {
    // Given
    const band = createAnalysisBand();

    // When
    band.update({
      meters: [
        { label: "Полоса", value: "н/д", unit: "Гц", reason: REASON_NO_ARTIFACT },
        { label: "Циклов", value: "н/д", reason: REASON_BRANCH },
        { label: "μ иглы", value: "1.2905", unit: "В" },
      ],
      peaks: [],
    });

    // Then
    const cells = band.root.querySelectorAll(".band-scalars .band-cell");
    expect(cells).toHaveLength(3);
    const first = cells[0];
    const bandDd = first?.querySelector("dd");
    expect(bandDd?.textContent).toBe("н/дГц");
    // Соседний узел: span сразу после dd, видимый текст причины + data-role.
    const reason = first?.querySelector("dd + span.band-cell-reason");
    expect(reason?.getAttribute("data-role")).toBe("band-reason");
    expect(reason?.textContent).toBe(REASON_NO_ARTIFACT);
    expect(reason?.getAttribute("title")).toBe(REASON_NO_ARTIFACT);
    expect(cells[1]?.querySelector("dd + span.band-cell-reason")?.textContent).toBe(REASON_BRANCH);
    // Причины нет — узла нет; title на dd — бонусный дубликат словаря.
    expect(cells[2]?.querySelector("span.band-cell-reason")).toBeNull();
    expect(bandDd?.getAttribute("title")).toBe(REASON_NO_ARTIFACT);
    expect(cells[2]?.querySelector("dd")?.getAttribute("title")).toBeNull();
  });
});
