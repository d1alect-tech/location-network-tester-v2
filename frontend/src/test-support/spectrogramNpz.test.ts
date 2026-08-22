/** Тест сборщика NPZ-фикстур (todo 42): STORED-контейнер должен читаться
 * продуктовым readNpzArrays — форма power_db (полосы, время), NaN сохраняется. */

import { describe, expect, it } from "vitest";
import { readNpzArrays } from "../components/charts/npz";
import { buildSpectrogramNpz } from "./spectrogramNpz";

describe("сборка NPZ-спектрограммы для e2e", () => {
  it("контейнер читается продуктовым парсером без потерь", async () => {
    const timeS = [0, 0.5, 1];
    const frequencyHz = [0, 10];
    const powerDb = new Float32Array([1, 2, 3, 4, 5, Number.NaN]);
    const buffer = buildSpectrogramNpz({ timeS, frequencyHz, powerDb });
    const arrays = await readNpzArrays(buffer, ["time_s", "frequency_hz", "power_db"]);
    const t = new Float64Array(arrays.get("time_s")!.data);
    const f = new Float64Array(arrays.get("frequency_hz")!.data);
    const p = new Float32Array(arrays.get("power_db")!.data);
    expect(Array.from(t)).toEqual(timeS);
    expect(Array.from(f)).toEqual(frequencyHz);
    expect(Array.from(p.slice(0, 5))).toEqual([1, 2, 3, 4, 5]);
    expect(Number.isNaN(p[5] as number)).toBe(true);
    expect(arrays.get("power_db")!.shape).toEqual([2, 3]);
  });
});
