/** Todo 15: маркеры SA — чистая логика без DOM. Отсчёт уровня — порт
 * readoutAt инспекции (spectrumReadout.ts) на дБ-вход склада: ближайший
 * бин → максимум ±1 бин → параболический подъём в дБ. Лимит 4 маркера,
 * 5-й — отказ с причиной. Пики свипа → ChartPeak[] (как peaksFromDetail);
 * q_factor=null → NaN, полоса FWHM не рисуется (bandBounds отбросит). */

import { describe, expect, it } from "vitest";
import type { LiveSaPeak } from "../../api/types-live";
import { SA_MARKER_LIMIT, SaMarkers, peaksFromSweep, readoutDbAt } from "./saMarkers";

const FREQ = [1000, 1100, 1200];

describe("readoutDbAt (±1 бин + парабола в дБ)", () => {
  it("уточняет асимметричный пик параболой: частота и подъём уровня", () => {
    // Вершина левее центра: prev выше next → дельта бинов отрицательная.
    const readout = readoutDbAt(FREQ, [-31, -30, -39], 1100);
    expect(readout).not.toBeNull();
    expect(readout?.frequencyHz).toBeCloseTo(1060, 9);
    expect(readout?.levelDb).toBeCloseTo(-29.2, 9);
  });

  it("берёт максимум ±1 бин, а не ближайший бин к клику", () => {
    // Клик около 1100, но соседний бин 1000 выше — отсчёт по нему.
    const readout = readoutDbAt(FREQ, [-30, -40, -45], 1090);
    expect(readout).toEqual({ frequencyHz: 1000, levelDb: -30 });
  });

  it("плоская тройка бинов — без параболы, бин как есть", () => {
    expect(readoutDbAt(FREQ, [-30, -30, -30], 1100)).toEqual({
      frequencyHz: 1100,
      levelDb: -30,
    });
  });

  it("пустой вход и мусорная цель — отказ без выдумки", () => {
    expect(readoutDbAt([], [], 1100)).toBeNull();
    expect(readoutDbAt(FREQ, [-31, -30, -39], Number.NaN)).toBeNull();
  });
});

describe("SaMarkers (лимит 4, клиентские)", () => {
  const trace = { freq: FREQ, psdDb: [-31, -30, -39] };

  it("двигает только выбранный маркер и освобождает отдельный слот", () => {
    const markers = new SaMarkers();
    markers.place(trace, 1050);
    markers.place(trace, 1150);
    const second = markers.list()[1];
    markers.move(1, { freq: [100, 200, 300], psdDb: [-60, -20, -60] }, 200);
    expect(markers.list()[0]).toMatchObject({ id: 1, frequencyHz: 200, levelDb: -20 });
    expect(markers.list()[1]).toEqual(second);
    markers.remove(1);
    expect(markers.list()).toEqual([second]);
  });

  it("обновляет уровень нового свипа, сохраняя частоту маркера", () => {
    const markers = new SaMarkers();
    markers.place(trace, 1100);
    markers.refresh({ freq: FREQ, psdDb: [-41, -40, -49] });
    expect(markers.list()[0]?.frequencyHz).toBe(1060);
    expect(markers.list()[0]?.levelDb).toBeCloseTo(-39.2);
    markers.refresh({ freq: [2000, 3000], psdDb: [-20, -30] });
    expect(markers.list()[0]?.levelDb).toBeNaN();
  });

  it("ставит маркеры с порядковыми id и отсчётом", () => {
    const markers = new SaMarkers();
    const first = markers.place(trace, 1050);
    const second = markers.place(trace, 1150);
    expect(first).toEqual({ kind: "placed", marker: { id: 1, frequencyHz: 1060, levelDb: -29.2 } });
    expect(second?.kind).toBe("placed");
    if (second?.kind === "placed") expect(second.marker.id).toBe(2);
    expect(markers.list()).toHaveLength(2);
  });

  it("пятый маркер отклоняется: лимит, склад не тронут", () => {
    const markers = new SaMarkers();
    for (let i = 0; i < SA_MARKER_LIMIT; i += 1) markers.place(trace, 1050 + i);
    const fifth = markers.place(trace, 1090);
    expect(fifth).toEqual({ kind: "rejected", reason: "limit" });
    expect(markers.list()).toHaveLength(SA_MARKER_LIMIT);
  });

  it("без трассы отсчёта нет — отказ no-trace, маркер не ставится", () => {
    const markers = new SaMarkers();
    expect(markers.place(null, 1100)).toEqual({ kind: "rejected", reason: "no-trace" });
    expect(markers.list()).toHaveLength(0);
  });

  it("сброс освобождает слоты, нумерация идёт дальше", () => {
    const markers = new SaMarkers();
    markers.place(trace, 1050);
    markers.clear();
    expect(markers.list()).toHaveLength(0);
    const again = markers.place(trace, 1060);
    if (again?.kind === "placed") expect(again.marker.id).toBe(2);
    else expect(again?.kind).toBe("placed");
  });
});

describe("peaksFromSweep (пики свипа → аннотации)", () => {
  it("маппит WirePeaks в ChartPeak, q=null → NaN (без полосы FWHM)", () => {
    const peaks: LiveSaPeak[] = [
      { frequency_hz: 3000, level_db: -30, prominence_db: 30, q_factor: 12.5 },
      { frequency_hz: 1500, level_db: -42, prominence_db: 12, q_factor: null },
    ];
    expect(peaksFromSweep(peaks)).toEqual([
      { frequency_hz: 3000, level_db: -30, prominence_db: 30, q_factor: 12.5 },
      { frequency_hz: 1500, level_db: -42, prominence_db: 12, q_factor: Number.NaN },
    ]);
  });

  it("отбрасывает мусорные частоты и уровни, порядок сервера сохраняется", () => {
    const peaks: LiveSaPeak[] = [
      { frequency_hz: Number.NaN, level_db: -30, prominence_db: 30, q_factor: 1 },
      { frequency_hz: 2000, level_db: -40, prominence_db: 8, q_factor: null },
      { frequency_hz: 1000, level_db: Number.NaN, prominence_db: 3, q_factor: null },
    ];
    expect(peaksFromSweep(peaks)).toEqual([
      { frequency_hz: 2000, level_db: -40, prominence_db: 8, q_factor: Number.NaN },
    ]);
    expect(peaksFromSweep([])).toEqual([]);
  });
});
