/** Тесты преобразований рядов для uPlot (todo 41).
 * Экстремумы: min/max-прореживание обязано сохранять иглу (spike) точно. */

import { describe, expect, it } from "vitest";
import {
  decimateMinMax,
  filterLogSafePairs,
  globalExtremes,
  psdToAsd,
  psdToDb,
  seriesToCsv,
} from "./series";

describe("decimateMinMax — сохранение экстремумов", () => {
  it("ряд короче бюджета возвращается без изменений", () => {
    const x = [0, 1, 2, 3];
    const y = [5, -1, 3, 2];
    const out = decimateMinMax(x, y, 10);
    expect(out.x).toEqual([0, 1, 2, 3]);
    expect(out.y).toEqual([5, -1, 3, 2]);
  });

  it("одиночная игла внутри ряда сохраняется точно при сильном прореживании", () => {
    // 20 000 точек, нули с единственной иглой 1000 в позиции 7000.
    const n = 20_000;
    const spikeIndex = 7_000;
    const x: number[] = new Array(n);
    const y: number[] = new Array(n).fill(0);
    for (let i = 0; i < n; i += 1) x[i] = i;
    y[spikeIndex] = 1000;

    const out = decimateMinMax(x, y, 2_000);

    expect(out.y).toContain(1000);
    expect(out.y.filter((v) => v === 1000)).toHaveLength(1);
    const extremes = globalExtremes(out.y);
    expect(extremes).toEqual({ min: 0, max: 1000 });
    // Игла осталась на своём x.
    const keptSpikeX = out.x[out.y.indexOf(1000)];
    expect(keptSpikeX).toBe(spikeIndex);
  });

  it("краевые экстремумы (первая и последняя точки) сохраняются", () => {
    const n = 10_000;
    const x = Array.from({ length: n }, (_, i) => i);
    const y = Array.from({ length: n }, (_, i) => Math.sin(i / 500) + (i === n - 1 ? -9 : 0));
    const out = decimateMinMax(x, y, 500);
    expect(out.y.at(0)).toBe(y[0]);
    expect(out.y.at(-1)).toBe(y[n - 1]);
  });
});

describe("filterLogSafePairs — детерминированная очистка для log-осей", () => {
  it("отбрасывает пары с нечисловыми значениями и значениями ≤ 0", () => {
    const x = [1, 0, -2, 4, Number.NaN, 6, Number.POSITIVE_INFINITY];
    const y = [1, 2, 3, 0, 5, Number.NaN, 7];
    const out = filterLogSafePairs(x, y);
    expect(out.x).toEqual([1]);
    expect(out.y).toEqual([1]);
  });

  it("устойчив к разной длине входных массивов (берёт минимум)", () => {
    const out = filterLogSafePairs([1, 2, 3, 4], [1, 2]);
    expect(out.x).toEqual([1, 2]);
    expect(out.y).toEqual([1, 2]);
  });
});

describe("единицы спектра", () => {
  it("PSD → дБ и ASD считаются по формулам 10·lg и √", () => {
    expect(psdToDb([1, 10, 100])).toEqual([0, 10, 20]);
    expect(psdToAsd([4, 9])).toEqual([2, 3]);
  });
});

describe("seriesToCsv", () => {
  it("формирует CSV с заголовком и строками данных", () => {
    const csv = seriesToCsv(
      ["frequency_hz", "psd_v2_per_hz"],
      [
        [10, 0.5],
        [20, 1.5],
      ],
    );
    expect(csv).toBe("frequency_hz,psd_v2_per_hz\n10,0.5\n20,1.5");
  });
});
