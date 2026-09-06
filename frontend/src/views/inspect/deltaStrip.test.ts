import { afterEach, describe, expect, it } from "vitest";
import type { SpectrumPayload } from "../../api/types-plots";
import { DELTA_STRIP_STORAGE_KEY, createDeltaStrip } from "./deltaStrip";

function payload(psd: number[]): SpectrumPayload {
  return { frequency_hz: [10, 20], psd_v2_per_hz: psd, point_count: 2 };
}

afterEach(() => {
  window.localStorage.removeItem(DELTA_STRIP_STORAGE_KEY);
});

describe("createDeltaStrip", () => {
  it("дефолт раскрыт, без пары — приглашение", () => {
    const strip = createDeltaStrip();
    expect(strip.isOpen()).toBe(true);
    expect(strip.root.querySelector("[data-delta-toggle]")?.getAttribute("aria-expanded")).toBe(
      "true",
    );
    strip.paint(null, null);
    expect((strip.root.querySelector("[data-delta-empty]") as HTMLElement).hidden).toBe(false);
  });

  it("пара гасит приглашение, paint не падает без canvas-контекста", () => {
    const strip = createDeltaStrip();
    strip.paint(payload([1, 1]), payload([1, 10]));
    expect((strip.root.querySelector("[data-delta-empty]") as HTMLElement).hidden).toBe(true);
  });

  it("тумблер сворачивает и помнит состояние", () => {
    const strip = createDeltaStrip();
    (strip.root.querySelector("[data-delta-toggle]") as HTMLButtonElement).click();
    expect(strip.isOpen()).toBe(false);
    expect(window.localStorage.getItem(DELTA_STRIP_STORAGE_KEY)).toBe("closed");
    const reopened = createDeltaStrip();
    expect(reopened.isOpen()).toBe(false);
    expect(reopened.root.classList.contains("is-closed")).toBe(true);
  });
});
