import { describe, expect, it } from "vitest";
import {
  currentRevision,
  deriveQcVerdict,
  isExcluded,
  proposeMember,
  transitionMember,
  undoLastDecision,
} from "./memberQc";

describe("memberQc (todo 43, red-first)", () => {
  it("exclusion undo restores the member with a compensating audit revision", () => {
    let member = proposeMember("sess-1", "user:op", "создан из выбора сессий");
    member = transitionMember(member, "included", "user:op", "QC пройден");
    member = transitionMember(member, "excluded", "user:op", "qc_clipping");
    expect(isExcluded(member)).toBe(true);

    const undone = undoLastDecision(member, "user:op", "оператор отменил исключение");
    // Восстановление: состояние вернулось к included.
    expect(isExcluded(undone)).toBe(false);
    // Аудит: исходное решение НЕ удалено, добавлена компенсирующая revision.
    expect(undone.history).toHaveLength(4);
    const last = undone.history[3];
    expect(last?.undo_of_revision).toBe(3);
    expect(last?.state).toBe("included");
    expect(currentRevision(member)).toBe(3);
    expect(currentRevision(undone)).toBe(4);
  });

  it("maps session health to a reason-coded QC verdict without color-only cues", () => {
    expect(deriveQcVerdict("ok")).toEqual({
      tone: "ok",
      label: "QC пройден",
      recommended_state: null,
      reason_code: null,
    });
    const corrupt = deriveQcVerdict("corrupt_manifest");
    expect(corrupt.recommended_state).toBe("excluded");
    expect(corrupt.reason_code).toBe("qc_corrupt_manifest");
    expect(corrupt.tone).toBe("error");
    expect(corrupt.label.length).toBeGreaterThan(0);
  });

  it("unknown health codes stay explicit instead of silently passing QC", () => {
    const unknown = deriveQcVerdict("что-то-новое");
    expect(unknown.tone).toBe("warn");
    expect(unknown.reason_code).toBe("qc_unknown_health");
    expect(unknown.label).toContain("Неизвестн");
  });
});
