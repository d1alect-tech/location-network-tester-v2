/** Todo 14 RED: клиентский склад трасс SA. Сервер трасс не хранит —
 * вкладка сама держит clear-write/min-hold/max-hold/running-average на
 * общей сетке частот. Инварианты: max-hold только растёт (до clear),
 * min-hold только падает, среднее — бегущее; смена полосы меняет сетку —
 * склад перечитывает её и перезапускает статистику; бюджет точек
 * ≤ 5000 на трассу не превышается никогда; мусорный вход не трогает склад. */

import { describe, expect, it } from "vitest";
import { SA_TRACE_POINT_BUDGET, SaTraceStore } from "./saTraceStore";

const GRID_A = [0, 100, 200, 300];
const GRID_B = [1000, 2000, 3000];

function values(...items: number[]): number[] {
  return items;
}

describe("SaTraceStore: трассы и статистика", () => {
  it("первый свип сеет все четыре трассы значением входа", () => {
    const store = new SaTraceStore();
    expect(store.applyTrace(GRID_A, values(-40, -30, -20, -10))).toBe(true);
    expect([...(store.freq() ?? [])]).toEqual(GRID_A);
    expect([...(store.trace("clear") ?? [])]).toEqual([-40, -30, -20, -10]);
    expect([...(store.trace("max") ?? [])]).toEqual([-40, -30, -20, -10]);
    expect([...(store.trace("min") ?? [])]).toEqual([-40, -30, -20, -10]);
    expect([...(store.trace("avg") ?? [])]).toEqual([-40, -30, -20, -10]);
    expect(store.sweepCount()).toBe(1);
  });

  it("max-hold только растёт: ниже вход не опускается, clear сбрасывает", () => {
    const store = new SaTraceStore();
    store.applyTrace(GRID_A, values(-40, -30, -20, -10));
    store.applyTrace(GRID_A, values(-45, -25, -25, -15));
    expect([...(store.trace("max") ?? [])]).toEqual([-40, -25, -20, -10]);
    store.applyTrace(GRID_A, values(-60, -60, -60, -60));
    expect([...(store.trace("max") ?? [])]).toEqual([-40, -25, -20, -10]);

    store.clear();
    expect(store.trace("max")).toBeNull();
    store.applyTrace(GRID_A, values(-45, -25, -25, -15));
    expect([...(store.trace("max") ?? [])]).toEqual([-45, -25, -25, -15]);
  });

  it("min-hold только падает: выше вход не поднимается", () => {
    const store = new SaTraceStore();
    store.applyTrace(GRID_A, values(-40, -30, -20, -10));
    store.applyTrace(GRID_A, values(-45, -25, -25, -15));
    expect([...(store.trace("min") ?? [])]).toEqual([-45, -30, -25, -15]);
    store.applyTrace(GRID_A, values(-10, -10, -10, -10));
    expect([...(store.trace("min") ?? [])]).toEqual([-45, -30, -25, -15]);
  });

  it("running-average — бегущее среднее всех свипов сетки", () => {
    const store = new SaTraceStore();
    store.applyTrace(GRID_A, values(0, 30, 0, 30));
    store.applyTrace(GRID_A, values(30, 0, 30, 0));
    expect([...(store.trace("avg") ?? [])]).toEqual([15, 15, 15, 15]);
    store.applyTrace(GRID_A, values(60, 60, 60, 60));
    expect([...(store.trace("avg") ?? [])]).toEqual([30, 30, 30, 30]);
    expect(store.sweepCount()).toBe(3);
  });

  it("clear-write перезаписывается последним свипом", () => {
    const store = new SaTraceStore();
    store.applyTrace(GRID_A, values(-40, -30, -20, -10));
    store.applyTrace(GRID_A, values(-11, -12, -13, -14));
    expect([...(store.trace("clear") ?? [])]).toEqual([-11, -12, -13, -14]);
  });

  it("clear стирает всё: сетка, трассы и счётчик свипов", () => {
    const store = new SaTraceStore();
    store.applyTrace(GRID_A, values(-40, -30, -20, -10));
    store.clear();
    expect(store.freq()).toBeNull();
    expect(store.trace("clear")).toBeNull();
    expect(store.trace("avg")).toBeNull();
    expect(store.sweepCount()).toBe(0);
  });
});

describe("SaTraceStore: смена полосы и бюджет", () => {
  it("смена сетки (полосы) перечитывает её и перезапускает статистику", () => {
    const store = new SaTraceStore();
    store.applyTrace(GRID_A, values(-40, -30, -20, -10));
    store.applyTrace(GRID_A, values(-60, -60, -60, -60));
    expect(store.sweepCount()).toBe(2);

    store.applyTrace(GRID_B, values(-15, -10, -5));
    expect([...(store.freq() ?? [])]).toEqual(GRID_B);
    expect(store.sweepCount()).toBe(1);
    // Статистика перезапущена: холды и среднее сеются новым свипом.
    expect([...(store.trace("max") ?? [])]).toEqual([-15, -10, -5]);
    expect([...(store.trace("min") ?? [])]).toEqual([-15, -10, -5]);
    expect([...(store.trace("avg") ?? [])]).toEqual([-15, -10, -5]);
  });

  it("смена сетки при той же длине тоже перечитывается (значение изменилось)", () => {
    const store = new SaTraceStore();
    store.applyTrace([0, 100, 200], values(-10, -20, -30));
    store.applyTrace([0, 100, 250], values(-10, -20, -30));
    expect([...(store.freq() ?? [])]).toEqual([0, 100, 250]);
    expect(store.sweepCount()).toBe(1);
  });

  it("бюджет точек: 5000 вмещается, 5001 отклоняется без порчи склада", () => {
    const store = new SaTraceStore();
    const grid = Array.from({ length: SA_TRACE_POINT_BUDGET }, (_, i) => i);
    const psd = Array.from({ length: SA_TRACE_POINT_BUDGET }, () => -50);
    expect(store.applyTrace(grid, psd)).toBe(true);
    expect(store.freq()?.length).toBe(SA_TRACE_POINT_BUDGET);

    const oversizedGrid = Array.from({ length: SA_TRACE_POINT_BUDGET + 1 }, (_, i) => i);
    const oversizedPsd = Array.from({ length: SA_TRACE_POINT_BUDGET + 1 }, () => -50);
    expect(store.applyTrace(oversizedGrid, oversizedPsd)).toBe(false);
    expect(store.freq()?.length).toBe(SA_TRACE_POINT_BUDGET);
    expect(store.sweepCount()).toBe(1);
    // Бюджет держится и под нагрузкой: массивы не растут.
    for (let i = 0; i < 100; i += 1) store.applyTrace(grid, psd);
    expect(store.trace("max")?.length).toBe(SA_TRACE_POINT_BUDGET);
    expect(store.trace("min")?.length).toBe(SA_TRACE_POINT_BUDGET);
    expect(store.trace("avg")?.length).toBe(SA_TRACE_POINT_BUDGET);
    expect(store.trace("clear")?.length).toBe(SA_TRACE_POINT_BUDGET);
  });
});

describe("SaTraceStore: мусорный вход", () => {
  it("разброс длины, пустой вход и нечисловые уровни отклоняются", () => {
    const store = new SaTraceStore();
    expect(store.applyTrace([], [])).toBe(false);
    expect(store.applyTrace(GRID_A, [-1, -2, -3])).toBe(false);
    expect(store.applyTrace(GRID_A, [-1, -2, -3, Number.NaN])).toBe(false);
    expect(store.applyTrace([0, Number.POSITIVE_INFINITY, 2], [-1, -2, -3])).toBe(false);
    expect(store.freq()).toBeNull();
    expect(store.sweepCount()).toBe(0);
  });
});
