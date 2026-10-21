import { describe, expect, it } from "vitest";
import type { RippleQc, RippleSelection } from "../../../api/types-ripple";
import { reasonText } from "./rippleFormat";
import { QC_VISIBLE_BUDGET } from "./rippleQcFit";
import { qcView } from "./rippleViewParts";

const SELECTION: RippleSelection = {
  sample_start_index: 10_000,
  sample_end_index_exclusive: 40_000,
  sample_count: 30_000,
  sample_rate_hz: 10_000,
  realized_duration_s: 3,
  excluded_prefix_samples: 10_000,
  settling_prefix_samples_nominal: 10_000,
  settling_basis: "capture_start_assuming_preconnected",
  continuity_status: "host_contiguous_unverified",
  continuity_reason_codes: ["host_contiguous_unverified"],
};

const MANY_CODES = [
  "clipping_unknown",
  "clip_census_inconsistent",
  "nonfinite_samples",
  "known_gap",
  "settling_unknown",
  "settling",
  "empty_span",
  "insufficient_samples",
  "insufficient_segments",
  "baseline_incompatible",
  "baseline_missing",
  "baseline_calibration_identity_unknown",
  "stale_input",
  "some_unknown_machine_code",
];

function qcOf(reasonCodes: readonly string[]): RippleQc {
  return {
    clipping_assessment: "clip_census_inconsistent",
    clip_count_scope: "aggregate_saved_record_telemetry",
    clip_low_count: 123_456_789,
    clip_high_count: 987_654_321,
    nonfinite_count: 0,
    nonfinite_count_scope: "selected_span",
    record_nonfinite_count: 0,
    dropped_samples: 0,
    reason_codes: [...reasonCodes],
  };
}

describe("видимая строка QC при множестве кодов причин", () => {
  it("строка помещается в слот и честно считает не показанные коды", () => {
    const view = qcView(qcOf(MANY_CODES), SELECTION);
    expect(view.text.length, "видимая строка влезает в фиксированный слот").toBeLessThanOrEqual(
      QC_VISIBLE_BUDGET,
    );
    expect(view.hidden.length, "часть кодов не показана").toBeGreaterThan(0);
    expect(view.text, "видимая строка называет число не показанных кодов").toMatch(
      new RegExp(`ещё ${view.hidden.length} (код|кода|кодов) QC`),
    );
    expect(view.text, "многоточие не прячет содержимое").not.toContain("...");
  });

  it("не показанные коды — это ровно те, чей текст не попал в строку", () => {
    const view = qcView(qcOf(MANY_CODES), SELECTION);
    const distinct = [...new Set(MANY_CODES)];
    const expected = distinct
      .filter((code) => !view.omitted.includes(code) && !view.text.includes(reasonText(code)))
      .sort();
    expect([...view.hidden].sort(), "скрыты ровно те коды, чей текст не показан").toEqual(expected);
    expect(new Set(view.hidden).size, "скрытые коды не повторяются").toBe(view.hidden.length);
  });

  it("полный текст и все машинные коды остаются в title", () => {
    const view = qcView(qcOf(MANY_CODES), SELECTION);
    for (const text of [
      "клиппинг не определён",
      "разрыв записи",
      "установление не подтверждено",
      "идёт окно установления",
      "пустой интервал",
      "мало отсчётов",
      "мало сегментов спектра",
      "фон несовместим",
      "фон не приложен",
      "калибровка фона неизвестна",
      "входные файлы изменились",
      "some_unknown_machine_code",
    ]) {
      expect(view.title, `title сохраняет «${text}»`).toContain(text);
    }
    for (const code of MANY_CODES) {
      expect(view.title, `title сохраняет код ${code}`).toContain(code);
    }
  });

  it("data-qc-omitted по-прежнему значит «код уже показан строкой»", () => {
    const view = qcView(qcOf(MANY_CODES), SELECTION);
    expect(view.omitted, "оценка ценза уже показана строкой").toContain("clip_census_inconsistent");
    expect(view.omitted, "в omitted только коды артефакта").toEqual(
      MANY_CODES.filter((code) => view.omitted.includes(code)),
    );
    for (const code of view.omitted) {
      expect(view.hidden, `«${code}» показан, а не скрыт`).not.toContain(code);
    }
  });

  it("реальный артефакт кампании показан целиком и ничего не прячет", () => {
    const view = qcView(
      qcOf(["clipping_unknown", "clip_census_inconsistent"]).clipping_assessment ===
        "clip_census_inconsistent"
        ? {
            ...qcOf(["clipping_unknown", "clip_census_inconsistent"]),
            clip_low_count: 2,
            clip_high_count: 0,
          }
        : qcOf([]),
      SELECTION,
    );
    expect(view.text).toBe(
      "QC: ценз несогласован · клиппинг 2/0 · нечисловые 0 · непрерывность не подтверждена · клиппинг не определён",
    );
    expect(view.hidden, "у реального артефакта ничего не скрыто").toEqual([]);
    expect(view.text, "многоточие не прячет содержимое").not.toContain("...");
  });

  it("длинный неизвестный код не показывается, но считается и остаётся в title", () => {
    const long = "x".repeat(120);
    const view = qcView(qcOf([long, "known_gap"]), SELECTION);
    expect(view.hidden, "длинный код не показан").toContain(long);
    expect(view.title, "длинный код остаётся в title").toContain(long);
    expect(view.text.length).toBeLessThanOrEqual(QC_VISIBLE_BUDGET);
  });
});
