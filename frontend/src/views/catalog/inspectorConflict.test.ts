import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import type { ContextResponse } from "../../api/types";
import { conflictFromError, isRevisionConflict, mergeDraftOntoFresh } from "./inspectorConflict";

function freshContext(): ContextResponse {
  return {
    session_id: "capture-001",
    revision: 7,
    health: "ok",
    reason_codes: [],
    fields: {
      fs_hz: {
        kind: "number",
        value: 1_000_000,
        unit: "Гц",
        source: "profile",
        captured_at: "2026-08-01T10:00:00Z",
      },
      operator_note_inline: {
        kind: "string",
        value: "стенд-А",
        source: "user",
        captured_at: "2026-08-01T10:00:00Z",
      },
    },
    tags: ["самошум"],
    notes: "чужие заметки",
  };
}

describe("isRevisionConflict", () => {
  it("detects only the typed conflict error kind", () => {
    expect(isRevisionConflict(new ApiError("conflict", { status: 409 }))).toBe(true);
    expect(isRevisionConflict(new ApiError("http", { status: 500 }))).toBe(false);
    expect(isRevisionConflict(new Error("обычная ошибка"))).toBe(false);
    expect(isRevisionConflict(null)).toBe(false);
  });
});

describe("conflictFromError", () => {
  it("builds a typed conflict carrying the stale revision and a Russian message", () => {
    const info = conflictFromError(3, new ApiError("conflict", { status: 409 }));
    expect(info.kind).toBe("revision_conflict");
    expect(info.expectedRevision).toBe(3);
    expect(info.message).toContain("Конфликт версий");
    expect(info.message).toContain("3");
  });
});

describe("mergeDraftOntoFresh", () => {
  it("re-applies the user draft on top of the freshly loaded revision", () => {
    const fresh = freshContext();
    const request = mergeDraftOntoFresh(fresh, {
      notes: "мои правки",
      tags: ["самошум", "повтор"],
      userFields: { operator_note_inline: "стенд-Б" },
    });
    expect(request.expected_revision).toBe(7);
    // Автоматические поля сохраняются, пользовательское поле заменено.
    if (!request.fields || !request.fields.fs_hz) throw new Error("fs_hz must survive merge");
    expect(request.fields.fs_hz.value).toBe(1_000_000);
    expect(request.fields.operator_note_inline?.value).toBe("стенд-Б");
    expect(request.notes).toBe("мои правки");
    expect(request.tags).toEqual(["самошум", "повтор"]);
  });

  it("never targets the stale revision that produced the conflict", () => {
    const fresh = freshContext();
    const request = mergeDraftOntoFresh(fresh, { notes: null, tags: [], userFields: {} });
    expect(request.expected_revision).not.toBe(3);
    expect(request.expected_revision).toBe(fresh.revision);
  });
});
