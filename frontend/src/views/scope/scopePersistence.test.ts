/** Todo 11 RED: послесвечение осциллографа — аккумулятор интенсивности
 * 256 уровней (0..255). Покрывается: нарастание уровня повторными
 * попаданиями с насыщением, затухание до нуля целочисленным шагом,
 * прижимание точек за пределами диапазона к краю сетки, пропуск
 * неконечных значений без исключений. */

import { describe, expect, it } from "vitest";
import { PERSISTENCE_GRID_H, PERSISTENCE_HIT_LEVEL, ScopePersistence } from "./scopePersistence";

describe("ScopePersistence: аккумулятор растёт и насыщается", () => {
  it("повторные попадания в ячейку наращивают уровень, потолок — 255", () => {
    // Given: сетка пуста; точка (t=0, v=0) при диапазоне ±5 В.
    const store = new ScopePersistence();
    expect(store.litCells()).toBe(0);

    // When: один и тот же кадр кладётся трижды без затухания.
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL * 2);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);

    // Then: уровень насыщен на максимуме шкалы и не переливается.
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(255);
    store.pushChannel([0, 0.001], [0, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(255);
  });

  it("пустой pushChannel (нет точек) не трогает аккумулятор", () => {
    const store = new ScopePersistence();
    store.pushChannel([], [], -5, 5);
    expect(store.litCells()).toBe(0);
  });
});

describe("ScopePersistence: затухание", () => {
  it("шаг затухания ×220/256 понижает уровень и доводит его до нуля", () => {
    // Given: одна точка уровня 96 (t=0 — вырожденная сетка времени, x=0).
    const store = new ScopePersistence();
    store.pushChannel([0], [0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL);

    // When: первый шаг затухания.
    store.decay();

    // Then: 96 × 220 / 256 = 82,5 → 82 (целочисленный пол).
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(82);

    // When: ещё 39 шагов — след гаснет до нуля, не «висит» на единице.
    for (let i = 0; i < 39; i += 1) store.decay();
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(0);
    expect(store.litCells()).toBe(0);
  });

  it("clear гасит аккумулятор целиком", () => {
    const store = new ScopePersistence();
    store.pushChannel([0, 0.001], [1, -1], -5, 5);
    expect(store.litCells()).toBeGreaterThan(0);
    store.clear();
    expect(store.litCells()).toBe(0);
  });
});

describe("ScopePersistence: границы сетки", () => {
  it("вольты за пределами диапазона прижимаются к краю, не бросают исключение", () => {
    const store = new ScopePersistence();
    store.pushChannel([0], [100], -5, 5);
    store.pushChannel([0], [-100], -5, 5);
    expect(store.levelAt(0, 0)).toBe(PERSISTENCE_HIT_LEVEL);
    expect(store.levelAt(0, PERSISTENCE_GRID_H - 1)).toBe(PERSISTENCE_HIT_LEVEL);
  });

  it("неконечные точки пропускаются, конечные рядом — пишутся", () => {
    const store = new ScopePersistence();
    store.pushChannel([0, 0.001], [Number.NaN, 0], -5, 5);
    expect(store.levelAt(0, PERSISTENCE_GRID_H / 2)).toBe(0);
    expect(store.levelAt(511, PERSISTENCE_GRID_H / 2)).toBe(PERSISTENCE_HIT_LEVEL);
  });

  it("вырожденный диапазон вольт не делит на ноль", () => {
    const store = new ScopePersistence();
    expect(() => store.pushChannel([0], [0], 0, 0)).not.toThrow();
    expect(store.litCells()).toBeGreaterThan(0);
  });
});
