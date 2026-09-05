/** C2: числовая форма окна спектрограммы — лист spectrogramWindowForm. */

import { describe, expect, it, vi } from "vitest";

import { tileRequestForRange } from "./spectrogramModel";
import type { SpectrogramLevel } from "./spectrogramModel";
import { createSpectrogramWindowForm } from "./spectrogramWindowForm";

function fakeLevel(): SpectrogramLevel {
  return {
    timeS: new Float64Array([0, 1, 2, 3]),
    frequencyHz: new Float64Array([10, 20, 30]),
    powerDb: new Float32Array(12),
    timeBins: 4,
    bands: 3,
  };
}

describe("форма окна спектрограммы", () => {
  it("renders four labeled inputs and the apply button", () => {
    const form = createSpectrogramWindowForm({
      getLevel: () => null,
      applyTile: () => Promise.resolve(),
      showError: () => undefined,
    });
    expect(form.tStart.getAttribute("aria-label")).toBe("Начало окна, с");
    expect(form.tEnd.getAttribute("aria-label")).toBe("Конец окна, с");
    expect(form.fLow.getAttribute("aria-label")).toBe("Нижняя граница окна, Гц");
    expect(form.fHigh.getAttribute("aria-label")).toBe("Верхняя граница окна, Гц");
    expect(form.applyWindowButton.textContent).toBe("Обновить окно");
    expect(form.fields).toHaveLength(5);
  });

  it("asks to build the spectrogram first when the level is missing", () => {
    const showError = vi.fn();
    const applyTile = vi.fn();
    const form = createSpectrogramWindowForm({
      getLevel: () => null,
      applyTile,
      showError,
    });
    form.applyWindowButton.click();
    expect(showError).toHaveBeenCalledWith("Сначала постройте спектрограмму.");
    expect(applyTile).not.toHaveBeenCalled();
  });

  it("requests the exact bbox tile for valid numeric input", () => {
    const level = fakeLevel();
    const applyTile = vi.fn();
    const showError = vi.fn();
    const form = createSpectrogramWindowForm({ getLevel: () => level, applyTile, showError });
    form.tStart.value = "0";
    form.tEnd.value = "2";
    form.fLow.value = "10";
    form.fHigh.value = "20";
    form.applyWindowButton.click();
    expect(showError).not.toHaveBeenCalled();
    expect(applyTile).toHaveBeenCalledTimes(1);
    expect(applyTile.mock.calls[0]?.[0]).toEqual(tileRequestForRange(level, 0, 2, 10, 20));
  });

  it("surfaces tile-range errors through the banner idiom", () => {
    const level = fakeLevel();
    const showError = vi.fn();
    const form = createSpectrogramWindowForm({
      getLevel: () => level,
      applyTile: () => Promise.resolve(),
      showError,
    });
    form.tStart.value = "99";
    form.tEnd.value = "100";
    form.fLow.value = "10";
    form.fHigh.value = "20";
    form.applyWindowButton.click();
    expect(showError).toHaveBeenCalledTimes(1);
    expect(typeof showError.mock.calls[0]?.[0]).toBe("string");
  });

  it("syncs inputs from native window changes", () => {
    const form = createSpectrogramWindowForm({
      getLevel: () => null,
      applyTile: () => Promise.resolve(),
      showError: () => undefined,
    });
    form.syncFromWindow(0.5, 1.5, 10, 30);
    expect(form.tStart.value).toBe("0.5");
    expect(form.tEnd.value).toBe("1.5");
    expect(form.fLow.value).toBe("10");
    expect(form.fHigh.value).toBe("30");
  });
});
