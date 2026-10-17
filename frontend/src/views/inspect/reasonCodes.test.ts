import { describe, expect, it } from "vitest";
import { REASON_CODE_RU, reasonCodeRu } from "./reasonCodes";

/** Коды из DECLARED_CODES семейств characterization-v1 — это shipped-copy. */
describe("reasonCodeRu: коды 18 семейств", () => {
  it("переводит код фазовой опоры фразой прототипа", () => {
    expect(reasonCodeRu("phase_reference_unavailable")).toBe("нет фазовой опоры F01");
  });

  it("переводит код вне-сеточной циклической частоты фразой прототипа", () => {
    expect(reasonCodeRu("cyclic_frequency_off_grid")).toBe("циклическая частота вне сетки");
  });

  it("переводит лимит артефакта фразой прототипа", () => {
    expect(reasonCodeRu("artifact_limit")).toBe("превышен лимит артефакта");
  });

  it("переводит нехватку поддержки фразой прототипа", () => {
    expect(reasonCodeRu("insufficient_support")).toBe("недостаточно поддержки");
  });

  it("переводит код, которого нет в прототипе, собственным словарём", () => {
    // minimum_frames_not_met в прототипе — опечатка; бэкенд объявляет insufficient_frames.
    expect(reasonCodeRu("insufficient_frames")).toBe("не набрано минимум кадров");
    expect(REASON_CODE_RU.minimum_frames_not_met).toBeUndefined();
  });
});

describe("reasonCodeRu: запасной путь", () => {
  it("показывает неизвестный код дословно, а не молчит", () => {
    const phrase = reasonCodeRu("quantum_flux_unavailable");

    expect(phrase).toContain("quantum_flux_unavailable");
    expect(phrase).toBe("неизвестный код: quantum_flux_unavailable");
  });

  it("различает пустой код и отсутствие кода", () => {
    expect(reasonCodeRu("")).toBe("код причины не указан");
    expect(reasonCodeRu("  ")).toBe("код причины не указан");
  });

  it("не отдаёт пустую фразу ни для одного словарярного кода", () => {
    const empty = Object.entries(REASON_CODE_RU)
      .filter(([, phrase]) => phrase.trim().length === 0)
      .map(([code]) => code);

    expect(empty).toEqual([]);
  });

  it("печатает каждый код дословно в том же виде, каким его отдаёт бэкенд", () => {
    const drifted = Object.entries(REASON_CODE_RU)
      .filter(([code]) => reasonCodeRu(code) === `неизвестный код: ${code}`)
      .map(([code]) => code);

    expect(drifted).toEqual([]);
  });
});
