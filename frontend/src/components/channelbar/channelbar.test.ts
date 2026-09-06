import { describe, expect, it } from "vitest";
import {
  CHANNELBAR_DASH,
  createChannelbar,
  formatBandRange,
  formatChannelRbw,
  formatHz,
} from "./channelbar";

describe("createChannelbar", () => {
  it("показывает пять полей с прочерками до первой отрисовки", () => {
    const bar = createChannelbar();
    expect(bar.root.getAttribute("role")).toBe("group");
    for (const field of ["band", "rbw", "window", "detector", "segments"]) {
      const node = bar.root.querySelector(`[data-chbar="${field}"]`);
      expect(node?.textContent).toBe(CHANNELBAR_DASH);
    }
  });

  it("paint пишет значения, пустоту и null гасит в прочерк", () => {
    const bar = createChannelbar();
    bar.paint({ band: "3 кГц – 3 МГц", rbw: "45 Гц", window: "", detector: null });
    expect(bar.root.querySelector('[data-chbar="band"]')?.textContent).toBe("3 кГц – 3 МГц");
    expect(bar.root.querySelector('[data-chbar="window"]')?.textContent).toBe(CHANNELBAR_DASH);
    expect(bar.root.querySelector('[data-chbar="detector"]')?.textContent).toBe(CHANNELBAR_DASH);
  });
});

describe("formatHz/formatBandRange/formatChannelRbw", () => {
  it("выбирает единицу по величине", () => {
    expect(formatHz(45)).toBe("45 Гц");
    expect(formatHz(3000)).toBe("3 кГц");
    expect(formatHz(3_000_000)).toBe("3 МГц");
    expect(formatHz(2_400_000)).toBe("2,4 МГц");
  });

  it("диапазон форматирует каждый конец отдельно", () => {
    expect(formatBandRange(3000, 3_000_000)).toBe("3 кГц – 3 МГц");
    expect(formatBandRange(null, 100)).toBeNull();
    expect(formatBandRange(Number.NaN, 100)).toBeNull();
  });

  it("RBW умножает шаг на ENBW Ханна, мусор — в null", () => {
    expect(formatChannelRbw(30)).toBe("45 Гц");
    expect(formatChannelRbw(0)).toBeNull();
    expect(formatChannelRbw(null)).toBeNull();
  });
});
