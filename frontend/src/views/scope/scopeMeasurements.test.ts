/** Todo 10 RED: измерения кадра живого режима — чистые функции без DOM.
 * Истина аналитическая (синтетические синусы), никогда не из движка.
 * Частота — пересечение порога по фронту, зеркально триггеру
 * (instrument/trigger.py: prev < level && cur >= level); экстремумы
 * уточняются параболой по трём соседним отсчётам (паттерн
 * spectrumReadout.readoutAt). Нулевой/постоянный кадр измерений не
 * даёт: null → «—», никогда NaN. */

import { describe, expect, it } from "vitest";
import type { LiveChannelSeries } from "../../api/types-live";
import {
  formatDutyValue,
  formatFrequencyValue,
  formatMeasurement,
  formatPeriodValue,
  formatVoltsValue,
  measureSeries,
} from "./scopeMeasurements";

/** Синтетический синус: n точек на windowS секунд, амплитуда и фаза заданы. */
function sine(
  points: number,
  cycles: number,
  windowS: number,
  amplitudeV: number,
  phase = 0,
): LiveChannelSeries {
  const time_s: number[] = [];
  const voltage_v: number[] = [];
  for (let i = 0; i < points; i += 1) {
    const t = (i / points) * windowS;
    time_s.push(t);
    voltage_v.push(amplitudeV * Math.sin((2 * Math.PI * cycles * i) / points + phase));
  }
  return { time_s, voltage_v, point_count: points };
}

function zeros(points: number): LiveChannelSeries {
  return {
    time_s: Array.from({ length: points }, (_, i) => i * 1e-5),
    voltage_v: Array.from({ length: points }, () => 0),
    point_count: points,
  };
}

describe("measureSeries: синтетический синус 1 кГц сходится к истине", () => {
  it("ровная сетка (1000 точек, 5 периодов): Vpp/Vmax/Vmin/RMS/f/T/D", () => {
    const amplitude = 1.7;
    const m = measureSeries(sine(1000, 5, 0.005, amplitude), null);

    expect(m.vppV).not.toBeNull();
    expect(m.vppV ?? 0).toBeCloseTo(2 * amplitude, 3);
    expect(m.vmaxV ?? 0).toBeCloseTo(amplitude, 3);
    expect(m.vminV ?? 0).toBeCloseTo(-amplitude, 3);
    expect(m.rmsV ?? 0).toBeCloseTo(amplitude / Math.SQRT2, 3);
    expect(m.frequencyHz ?? 0).toBeCloseTo(1000, 1);
    expect(m.periodS ?? 0).toBeCloseTo(0.001, 6);
    expect(m.duty ?? 0).toBeCloseTo(0.5, 3);
  });

  it("косая сетка (137 точек, фаза π/7): парабола экстремумов держит истину", () => {
    const amplitude = 0.9;
    const m = measureSeries(sine(137, 3, 0.003, amplitude, Math.PI / 7), null);

    // Допуск сетки: половина шага дискретизации по фазе — refinment обязан
    // сходиться много лучше (сэмпл-максимум без параболы давал бы до 0.03%).
    expect(Math.abs((m.vppV ?? 0) - 2 * amplitude)).toBeLessThan(2 * amplitude * 0.001);
    expect(Math.abs((m.vmaxV ?? 0) - amplitude)).toBeLessThan(amplitude * 0.001);
    expect(Math.abs((m.vminV ?? 0) + amplitude)).toBeLessThan(amplitude * 0.001);
    expect(Math.abs((m.rmsV ?? 0) - amplitude / Math.SQRT2)).toBeLessThan(
      (amplitude / Math.SQRT2) * 0.001,
    );
    expect(Math.abs((m.frequencyHz ?? 0) - 1000)).toBeLessThan(2);
    expect(Math.abs((m.periodS ?? 0) - 0.001)).toBeLessThan(2e-6);
    expect(Math.abs((m.duty ?? 0) - 0.5)).toBeLessThan(0.002);
  });

  it("порог триггера ≠ середина: частота та же, duty по уровню (arcsin)", () => {
    // Синус выше уровня k·A занимает (π − 2·arcsin k)/2π периода.
    const amplitude = 1;
    const level = 0.5;
    const m = measureSeries(sine(2000, 8, 0.008, amplitude), level);

    expect(Math.abs((m.frequencyHz ?? 0) - 1000)).toBeLessThan(2);
    expect(m.duty ?? 0).toBeCloseTo(1 / 3, 3);
  });
});

describe("measureSeries: деградация и границы", () => {
  it("нулевой кадр — все измерения null (в UI «—», не NaN)", () => {
    const m = measureSeries(zeros(64), null);
    expect(m).toEqual({
      vppV: null,
      vmaxV: null,
      vminV: null,
      rmsV: null,
      frequencyHz: null,
      periodS: null,
      duty: null,
    });
  });

  it("постоянный сигнал без пересечений — тоже null по всей строке", () => {
    const flat: LiveChannelSeries = {
      time_s: [0, 1e-4, 2e-4],
      voltage_v: [2.5, 2.5, 2.5],
      point_count: 3,
    };
    expect(measureSeries(flat, null).frequencyHz).toBeNull();
    expect(measureSeries(flat, null).vppV).toBeNull();
  });

  it("меньше двух фронтов — частоты нет, амплитуды есть", () => {
    // Полпериода: один фронт вверх, второго нет.
    const half: LiveChannelSeries = {
      time_s: [0, 2.5e-4, 5e-4, 7.5e-4, 1e-3],
      voltage_v: [-1, -0.5, 0, 0.5, 1],
      point_count: 5,
    };
    const m = measureSeries(half, 0);
    expect(m.vmaxV).toBe(1);
    expect(m.vminV).toBe(-1);
    expect(m.vppV).toBe(2);
    expect(m.frequencyHz).toBeNull();
    expect(m.periodS).toBeNull();
    expect(m.duty).toBeNull();
  });

  it("семантика фронта — зеркало триггера: prev < level и cur >= level", () => {
    // Треугольник: фронты ровно на отсчёте уровня — двойного счёта нет,
    // время фронта — интерполяция между отсчётами.
    const tri: LiveChannelSeries = {
      time_s: [0, 1, 2, 3, 4, 5, 6].map((t) => t * 1e-3),
      voltage_v: [-1, 0, 1, 0, -1, 0, 1],
      point_count: 7,
    };
    const m = measureSeries(tri, 0);
    // Фронты: v0→v1 (−1<0, 0>=0) ровно на 1 мс и v4→v5 на 5 мс: период 4 мс.
    expect(m.frequencyHz).toBeCloseTo(250, 6);
    expect(m.periodS).toBeCloseTo(0.004, 9);
    // Спад v2→v3 (1>0, 0<=0) на 3 мс: высокий 2 мс, низкий 2 мс — 50%.
    expect(m.duty ?? 0).toBeCloseTo(0.5, 6);
  });

  it("пустой канал — все измерения null", () => {
    const empty: LiveChannelSeries = { time_s: [], voltage_v: [], point_count: 0 };
    expect(measureSeries(empty, null).vppV).toBeNull();
  });
});

describe("форматтеры измерений (ru-точность, точка как в scope-табе)", () => {
  it("вольты: В с 3 знаками, ниже 1 В — мВ без дроби", () => {
    expect(formatVoltsValue(2)).toBe("2.000 В");
    expect(formatVoltsValue(-0.5)).toBe("-500 мВ");
    expect(formatVoltsValue(0.039)).toBe("39 мВ");
  });

  it("частота и период: кГц/мс с 3 знаками, Гц с 1", () => {
    expect(formatFrequencyValue(1000)).toBe("1.000 кГц");
    expect(formatFrequencyValue(60)).toBe("60.0 Гц");
    expect(formatPeriodValue(0.001)).toBe("1.000 мс");
    expect(formatPeriodValue(5e-5)).toBe("50.000 мкс");
  });

  it("null форматируется в «—», число — своим форматтером", () => {
    expect(formatMeasurement(null, formatVoltsValue)).toBe("—");
    expect(formatMeasurement(2, formatVoltsValue)).toBe("2.000 В");
    expect(formatMeasurement(0.5, formatDutyValue)).toBe("50.0 %");
  });
});
