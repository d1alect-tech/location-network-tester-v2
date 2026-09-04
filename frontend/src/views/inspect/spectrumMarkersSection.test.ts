/** B3: селекторы RBW/окна + таблица маркеров (пики, дельты A/B, гармоники, СКЗ полосы).
 * RED: селекторы 10/30/50/100/300 и 4 окна; readout с параболой в дБ;
 * max-агрегация ±1 бин; подписи дБ с ref 1 В²/Гц; русские строки. */

import { describe, expect, it } from "vitest";
import type { SpectrumPayload } from "../../api/types-plots";
import { createSpectrumExtras } from "./spectrumExtras";
import { deltaAt, readoutAt } from "./spectrumReadout";
import { MARKER_RBW_OPTIONS, MARKER_WINDOW_OPTIONS } from "./spectrumSelectors";

function parabolaPayload(): SpectrumPayload {
  // Парабола в дБ с вершиной ровно между бинами 900/1000 (df=100): истина замкнутая.
  const frequency_hz = [800, 900, 1000, 1100, 1200];
  const psd_v2_per_hz = frequency_hz.map((f) => 10 ** ((-40 - 0.01 * (f - 950) ** 2) / 10));
  return { frequency_hz, psd_v2_per_hz, point_count: 5, resolution_hz: 100 };
}

function widePayload(scale = 1): SpectrumPayload {
  const frequency_hz = [100, 200, 400, 800, 1600, 3200];
  const psd_v2_per_hz = frequency_hz.map(
    (f) => scale * 10 ** ((-30 - 0.005 * (f - 400) ** 2) / 10),
  );
  return {
    frequency_hz,
    psd_v2_per_hz,
    point_count: 6,
    resolution_hz: 100,
    window: "hann",
    enbw_hz: 150,
  };
}

describe("readoutAt", () => {
  it("восстанавливает вершину параболы между бинами (частота и уровень)", () => {
    const readout = readoutAt(parabolaPayload(), 900);
    expect(readout?.frequencyHz).toBeCloseTo(950, 9);
    expect(readout?.levelDb).toBeCloseTo(-40, 9);
  });

  it("max-агрегация: игла в соседнем бине не теряется", () => {
    const payload = parabolaPayload();
    const readout = readoutAt(payload, 800);
    expect(readout).not.toBeNull();
    expect(readout?.levelDb ?? Number.NaN).toBeGreaterThan(-46);
  });

  it("null на пустом/битом payload", () => {
    expect(readoutAt({ frequency_hz: [], psd_v2_per_hz: [], point_count: 0 }, 100)).toBeNull();
    expect(
      readoutAt({ frequency_hz: [100], psd_v2_per_hz: [Number.NaN], point_count: 1 }, 100),
    ).toBeNull();
  });
});

describe("deltaAt", () => {
  it("считает Δ A−B в дБ по одной частоте", () => {
    expect(deltaAt(widePayload(1), widePayload(4), 400)).toBeCloseTo(6.0206, 3);
  });

  it("null без трассы B", () => {
    expect(deltaAt(widePayload(1), null, 400)).toBeNull();
  });
});

describe("createSpectrumExtras: селекторы", () => {
  it("пять RBW и четыре окна с русскими подписями", () => {
    const extras = createSpectrumExtras();
    const rbw = extras.selects.querySelector<HTMLSelectElement>("[data-spectrum-rbW-select]");
    const window = extras.selects.querySelector<HTMLSelectElement>("[data-spectrum-window-select]");
    expect([...MARKER_RBW_OPTIONS]).toEqual([10, 30, 50, 100, 300]);
    expect([...MARKER_WINDOW_OPTIONS]).toEqual(["hann", "flattop", "kaiser", "blackman"]);
    expect(rbw?.options.length).toBe(5);
    expect(window?.options.length).toBe(4);
    expect(extras.selects.textContent).toContain("RBW");
    expect(extras.selects.textContent).toContain("Окно");
  });

  it("paint выставляет окно/подпись из payload (RBW ≈ 150 Гц, ENBW, ref)", () => {
    const extras = createSpectrumExtras();
    extras.paint({ payloadA: widePayload(), payloadB: null, analysis: {} });
    const window = extras.selects.querySelector<HTMLSelectElement>("[data-spectrum-window-select]");
    expect(window?.value).toBe("hann");
    const meta = extras.selects.querySelector("[data-spectrum-selector-meta]");
    expect(meta?.textContent).toContain("RBW ≈ 150 Гц");
    expect(meta?.textContent).toContain("ENBW 150 Гц");
  });

  it("смена выбора показывает пометку про следующий анализ", () => {
    const extras = createSpectrumExtras();
    extras.paint({ payloadA: widePayload(), payloadB: null, analysis: {} });
    const rbw = extras.selects.querySelector<HTMLSelectElement>("[data-spectrum-rbW-select]");
    expect(rbw).not.toBeNull();
    if (rbw !== null) rbw.value = "300";
    rbw?.dispatchEvent(new Event("change", { bubbles: true }));
    const note = extras.selects.querySelector("[data-spectrum-selector-note]");
    expect(note?.textContent).toContain("при следующем анализе");
  });
});

describe("createSpectrumExtras: таблица маркеров", () => {
  const analysis = {
    spectrum: {
      peaks: [{ frequency_hz: 400, level_db: -30, prominence_db: 12, q_factor: 8 }],
    },
  };

  it("пики, дельты A/B и гармоника H2 с подписью дБ отн. 1 В²/Гц", () => {
    const extras = createSpectrumExtras();
    extras.paint({ payloadA: widePayload(1), payloadB: widePayload(4), analysis });
    const table = extras.markers.querySelector("[data-spectrum-markers-table]");
    expect(table?.textContent).toContain("Пик 1");
    expect(table?.textContent).toContain("H2");
    expect(table?.textContent).toContain("дБ (отн. 1 В²/Гц)");
    expect(table?.textContent).toContain("Δ A−B");
    expect(table?.textContent).toMatch(/\+6,0/);
  });

  it("без трассы B колонки дельт нет, строка СКЗ полосы есть", () => {
    const extras = createSpectrumExtras();
    extras.paint({ payloadA: widePayload(1), payloadB: null, analysis });
    const table = extras.markers.querySelector("[data-spectrum-markers-table]");
    expect(table?.textContent).not.toContain("Δ A−B");
    expect(table?.textContent).toContain("СКЗ полосы");
  });

  it("пустые пики дают строку-заглушку по-русски", () => {
    const extras = createSpectrumExtras();
    extras.paint({ payloadA: widePayload(1), payloadB: null, analysis: { spectrum: {} } });
    expect(extras.markers.textContent).toContain("Пики не найдены");
  });
});
