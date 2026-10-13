/** Todo 10 RED: модель курсоров осциллографа — чистые функции без DOM.
 * Курсоры времени — доли окна кадра [0..1], курсоры напряжения — вольты
 * в номинальной шкале CH1 (±5 В из дефолтного запроса запуска). Readout
 * Δt/ΔV — паттерн spectrumReadout: чистая функция + null на битых данных. */

import { describe, expect, it } from "vitest";
import {
  VOLT_CURSOR_SPAN_V,
  clampFraction,
  formatDeltaSecondsValue,
  formatDeltaVoltsValue,
  timeCursorDeltaSeconds,
  voltageCursorDeltaV,
} from "./scopeCursors";

describe("курсоры времени: Δt по окну кадра", () => {
  it("Δt — модуль разности долей, умноженный на окно кадра", () => {
    expect(timeCursorDeltaSeconds({ t1: 0.25, t2: 0.75 }, 0.001)).toBeCloseTo(0.0005, 12);
    expect(timeCursorDeltaSeconds({ t1: 0.75, t2: 0.25 }, 0.001)).toBeCloseTo(0.0005, 12);
  });

  it("нулевое окно (кадра нет) — null, UI покажет «—»", () => {
    expect(timeCursorDeltaSeconds({ t1: 0.1, t2: 0.9 }, 0)).toBeNull();
    expect(timeCursorDeltaSeconds({ t1: 0.1, t2: 0.9 }, null)).toBeNull();
  });

  it("доли за пределами [0..1] зажимаются", () => {
    expect(clampFraction(-0.5)).toBe(0);
    expect(clampFraction(1.5)).toBe(1);
    expect(clampFraction(0.3)).toBe(0.3);
  });
});

describe("курсоры напряжения: ΔV в номинальной шкале", () => {
  it("ΔV — модуль разности вольт", () => {
    expect(voltageCursorDeltaV({ v1: -1, v2: 2 })).toBe(3);
    expect(voltageCursorDeltaV({ v1: 2, v2: -1 })).toBe(3);
    expect(voltageCursorDeltaV({ v1: 0.5, v2: 0.539 })).toBeCloseTo(0.039, 12);
  });

  it("номинальная шкала курсоров — ±5 В (дефолт запуска CH1)", () => {
    expect(VOLT_CURSOR_SPAN_V).toBe(5);
  });
});

describe("форматтеры дельт (точка как в scope-табе)", () => {
  it("Δt: мс/мкс/нс, ΔV: В/мВ", () => {
    expect(formatDeltaSecondsValue(0.0005)).toBe("500.000 мкс");
    expect(formatDeltaSecondsValue(0.001)).toBe("1.000 мс");
    expect(formatDeltaVoltsValue(3)).toBe("3.000 В");
    expect(formatDeltaVoltsValue(0.039)).toBe("39 мВ");
  });

  it("null — «—», никогда NaN", () => {
    expect(formatDeltaSecondsValue(null)).toBe("—");
    expect(formatDeltaVoltsValue(null)).toBe("—");
  });
});
