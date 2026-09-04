/** Пик-детектор live-спектрограммы: MAX по лог-бину вместо nearestIndex.
 * RED: пик между сэмплами лог-сетки не должен теряться при ресемплинге. */

import { describe, expect, it } from "vitest";
import { LiveGramStore } from "./spectrogramLiveStore";

describe("LiveGramStore.pushSpectrumColumn: max-агрегация", () => {
  it("пик внутри лог-бина не теряется, даже если центр бина ближе к низкому сэмплу", () => {
    // Given: домен по умолчанию 1 кГц…10 МГц; сэмплы 1000 Гц (−20) и 1010 Гц (−80)
    // лежат в одном лог-бине 0, центр бина (~1018 Гц) ближе к низкому сэмплу.
    const store = new LiveGramStore();
    const freqs = [1000, 1010, 100_000, 1_000_000];
    const psdDb = [-20, -80, -50, -50];

    // When
    expect(store.pushSpectrumColumn(freqs, psdDb)).toBe(true);

    // Then: в бине — максимум PSD (в дБ max корректен как max PSD), а не nearest.
    const row = store.rowPhysical(0);
    expect(store.cellAt(row, 0)).toBe(-20);
  });

  it("пустой вход не трогает кольцо", () => {
    // Given
    const store = new LiveGramStore();

    // When / Then
    expect(store.pushSpectrumColumn([], [])).toBe(false);
    expect(store.pushSpectrumColumn([1000], [-50])).toBe(false);
    expect(store.columnCount()).toBe(0);
  });
});
