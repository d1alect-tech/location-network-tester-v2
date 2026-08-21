/** Типизированный конфликт revision контекста и поток «перечитать-объединить».
 * Конкурентная правка никогда не затирает чужие данные молча: при 409 UI
 * показывает типизированный конфликт, перечитывает свежую revision и
 * заново применяет черновик пользователя уже поверх актуальных данных. */

import { ApiError } from "../../api/errors";
import type { ContextField, ContextResponse, ContextUpdateRequest } from "../../api/types";

export interface RevisionConflict {
  kind: "revision_conflict";
  /** Revision, против которой выполнялась неудачная запись. */
  expectedRevision: number;
  message: string;
}

/** Распознаёт именно конфликт версий (409), а не любую ошибку API. */
export function isRevisionConflict(error: unknown): error is ApiError {
  return error instanceof ApiError && error.kind === "conflict";
}

/** Собирает типизированное описание конфликта с русским сообщением. */
export function conflictFromError(expectedRevision: number, error: ApiError): RevisionConflict {
  return {
    kind: "revision_conflict",
    expectedRevision,
    message: `Конфликт версий: запись велась против revision ${expectedRevision}. ${
      error.message
    } Перечитайте контекст и повторите сохранение.`,
  };
}

/** Черновик правок пользователя: заметки, метки тегов и пользовательские поля. */
export interface ContextDraft {
  notes: string | null;
  tags: string[];
  /** Ключ → новое текстовое значение пользовательских полей (source=user). */
  userFields: Record<string, string>;
}

/** Пользовательские строковые поля, доступные для редактирования в UI. */
export function userEditableFields(context: ContextResponse): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, field] of Object.entries(context.fields)) {
    if (field.source === "user" && field.kind === "string") {
      const value = field.value;
      if (typeof value === "string") result[key] = value;
    }
  }
  return result;
}

function applyDraftFields(
  fresh: ContextResponse,
  userFields: Record<string, string>,
): Record<string, ContextField> {
  const merged: Record<string, ContextField> = { ...fresh.fields };
  for (const [key, text] of Object.entries(userFields)) {
    const existing = merged[key];
    merged[key] =
      existing && typeof existing.value === "string"
        ? { ...existing, value: text }
        : {
            kind: "string",
            value: text,
            source: "user",
            collection_status: "collected",
            captured_at: new Date().toISOString(),
          };
  }
  return merged;
}

/** Повторно применяет черновик пользователя поверх СВЕЖЕЙ revision.
 * Автоматические и профильные поля сохраняются как есть; ожидаемая revision
 * берётся только из freshly-read ответа, никогда из устаревшего черновика. */
export function mergeDraftOntoFresh(
  fresh: ContextResponse,
  draft: ContextDraft,
): ContextUpdateRequest {
  return {
    expected_revision: fresh.revision,
    fields: applyDraftFields(fresh, draft.userFields),
    tags: [...draft.tags],
    notes: draft.notes,
  };
}
