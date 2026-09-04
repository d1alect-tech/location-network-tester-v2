/** C3: единицы отображения спектра — display-only сдвиги, хранимый формат тот же. */

import { describe, expect, it } from "vitest";
import {
  UNIT_OFFSET_DB,
  createUnitsControl,
  parseDisplayUnit,
  shiftLevelDb,
  unitRefLabel,
} from "./spectrumUnits";

describe("spectrumUnits: display-only пересчёт рядом с дБВ/Гц", () => {
  it("опора 1 В²/Гц — 0 дБВ, +120 дБмкВ, +10·log10(20) дБм в 50 Ом", () => {
    expect(UNIT_OFFSET_DB.dbv).toBe(0);
    expect(UNIT_OFFSET_DB.dbuv).toBe(120);
    expect(UNIT_OFFSET_DB.dbm50).toBeCloseTo(13.0103, 3);
    expect(shiftLevelDb(0, "dbv")).toBe(0);
    expect(shiftLevelDb(0, "dbuv")).toBe(120);
    expect(shiftLevelDb(0, "dbm50")).toBeCloseTo(13.0103, 3);
  });

  it("сдвиг линеен: −30 дБВ → 90 дБмкВ; дельты от единицы не зависят", () => {
    expect(shiftLevelDb(-30, "dbuv")).toBe(90);
    const deltaDbv = 6.0206;
    expect(shiftLevelDb(deltaDbv, "dbm50") - shiftLevelDb(0, "dbm50")).toBeCloseTo(deltaDbv, 9);
  });

  it("подписи называют опору честно, мусор парсится в null", () => {
    expect(unitRefLabel("dbv")).toContain("1 В²/Гц");
    expect(unitRefLabel("dbm50")).toContain("50 Ом");
    expect(parseDisplayUnit("dbx")).toBeNull();
    expect(parseDisplayUnit("dbm50")).toBe("dbm50");
  });

  it("тоггл по умолчанию — дБВ/Гц и зовёт onChange", () => {
    let calls = 0;
    const control = createUnitsControl(() => {
      calls += 1;
    });
    document.body.append(control.root);
    try {
      const select = control.root.querySelector<HTMLSelectElement>("[data-spectrum-unit-select]");
      expect(select?.value).toBe("dbv");
      expect(control.unit()).toBe("dbv");
      expect(control.root.textContent).toContain("Единицы");
      select?.dispatchEvent(new Event("change", { bubbles: true }));
      expect(calls).toBe(1);
    } finally {
      document.body.replaceChildren();
    }
  });
});
