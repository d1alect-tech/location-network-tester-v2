/** Инспектор контекста сессии V6: панель .panel (hd + bd), сводка
 * .readout-grid, таблица полей .tbl, редакторы .form-grid с .ctl,
 * восстановление .banner, конфликт revision .banner.banner-inline.
 * Логика без изменений: поля с источником/доступностью, правка заметок,
 * тегов и пользовательских полей, сохранение через PUT с оптимистичной
 * блокировкой; конфликт revision — типизированное состояние с потоком
 * «перечитать и объединить». Хук .lnt-cat-inspector и связки e2e
 * (.lnt-cat-session-summary, .lnt-cat-notes, .lnt-btn-primary) сохранены. */

import type { LntApiClient } from "../../api/client";
import type { ContextResponse, ContextUpdateRequest } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { createMutation, createResourceLoader } from "../../state/resource";
import { HEALTH_LABELS } from "./catalogModel";
import { createFieldsTable, createRecoveryPanel } from "./contextFieldsView";
import {
  type RevisionConflict,
  conflictFromError,
  isRevisionConflict,
  mergeDraftOntoFresh,
  userEditableFields,
} from "./inspectorConflict";
import { v6Field } from "./catalogV6Field";

export interface ContextInspectorOptions {
  client: LntApiClient;
}

export interface ContextInspectorHandle {
  root: HTMLElement;
  loadSession(sessionId: string): Promise<void>;
}

export function createContextInspector(options: ContextInspectorOptions): ContextInspectorHandle {
  const { client } = options;
  let currentSessionId: string | null = null;
  let conflict: RevisionConflict | null = null;

  const loader = createResourceLoader<ContextResponse>((key, signal) =>
    client.context(key, { signal }),
  );
  const saveMutation = createMutation<ContextUpdateRequest, ContextResponse>((request) => {
    if (currentSessionId === null) return Promise.reject(new Error("сессия не выбрана"));
    return client.updateContext(currentSessionId, request);
  });

  const summary = el("div", { className: "lnt-cat-session-summary readout-grid" });
  const recovery = el("div", {});
  const fieldsHost = el("div", {});
  const notesArea = document.createElement("textarea");
  notesArea.className = "ctl lnt-cat-notes";
  notesArea.rows = 4;
  const tagsInput = document.createElement("input");
  tagsInput.type = "text";
  tagsInput.className = "ctl";
  const userFieldsHost = el("div", { className: "form-grid" });
  const conflictPanel = el("div", { className: "banner banner-inline is-warn lnt-cat-conflict" });
  conflictPanel.hidden = true;
  const errorNote = el("p", { className: "banner banner-inline", attrs: { role: "alert" } });
  errorNote.hidden = true;
  const saveButton = el("button", {
    className: "btn lnt-btn lnt-btn-primary",
    text: "Сохранить",
    attrs: { type: "button" },
  });

  function setError(message: string): void {
    errorNote.textContent = message;
    errorNote.hidden = message === "";
  }

  function draftTags(): string[] {
    return tagsInput.value
      .split(",")
      .map((part) => part.trim())
      .filter((part) => part !== "");
  }

  function collectDraft(): { notes: string; tags: string[]; userFields: Record<string, string> } {
    const userFields: Record<string, string> = {};
    for (const input of userFieldsHost.querySelectorAll<HTMLInputElement>("input[data-field]")) {
      const key = input.getAttribute("data-field");
      if (key !== null) userFields[key] = input.value;
    }
    return { notes: notesArea.value, tags: draftTags(), userFields };
  }

  function buildRequest(context: ContextResponse): ContextUpdateRequest {
    const draft = collectDraft();
    return {
      expected_revision: context.revision,
      fields: mergeDraftOntoFresh(context, draft).fields,
      tags: draft.tags,
      notes: draft.notes,
    };
  }

  async function runSave(): Promise<void> {
    const state = loader.get();
    if (state.kind !== "ready") return;
    setError("");
    try {
      await client.ensureReady();
      await saveMutation.run(buildRequest(state.value));
      conflict = null;
      renderConflict();
      await loader.load(currentSessionId ?? state.value.session_id);
      announcePolite("Контекст сохранён");
    } catch (error) {
      if (isRevisionConflict(error)) {
        conflict = conflictFromError(state.value.revision, error);
        renderConflict();
        announcePolite("Конфликт версий: контекст изменён другим процессом");
      } else {
        setError(error instanceof Error ? error.message : "Не удалось сохранить изменения.");
      }
    }
  }

  saveButton.addEventListener("click", () => void runSave());

  function renderConflict(): void {
    while (conflictPanel.firstChild) conflictPanel.removeChild(conflictPanel.firstChild);
    if (conflict === null) {
      conflictPanel.hidden = true;
      return;
    }
    conflictPanel.hidden = false;
    conflictPanel.append(
      el("p", { className: "banner-msg", text: conflict.message }),
      buildMergeButton(),
      buildDiscardButton(),
    );
  }

  function buildMergeButton(): HTMLElement {
    const button = el("button", {
      className: "btn",
      text: "Перечитать и объединить",
      attrs: { type: "button" },
    });
    button.addEventListener("click", () => {
      void (async () => {
        const state = loader.get();
        if (state.kind !== "ready") return;
        // Черновик фиксируется ДО перечитывания: renderReady иначе затрёт
        // поля формы свежими данными, и объединение потеряло бы правки.
        const draft = collectDraft();
        await loader.load(state.value.session_id);
        const fresh = loader.get();
        if (fresh.kind !== "ready") return;
        try {
          await client.ensureReady();
          await saveMutation.run(mergeDraftOntoFresh(fresh.value, draft));
          conflict = null;
          renderConflict();
          await loader.load(fresh.value.session_id);
          announcePolite("Изменения применены поверх актуальной версии");
        } catch (retryError) {
          setError(
            retryError instanceof Error ? retryError.message : "Повторное сохранение не удалось.",
          );
        }
      })();
    });
    return button;
  }

  function buildDiscardButton(): HTMLElement {
    const button = el("button", {
      className: "btn btn-secondary",
      text: "Отбросить мои правки и перечитать",
      attrs: { type: "button" },
    });
    button.addEventListener("click", () => {
      conflict = null;
      renderConflict();
      const state = loader.get();
      if (state.kind === "ready") void loader.load(state.value.session_id);
    });
    return button;
  }

  function renderReady(context: ContextResponse): void {
    const health = HEALTH_LABELS[context.health as keyof typeof HEALTH_LABELS];
    while (summary.firstChild) summary.removeChild(summary.firstChild);
    summary.append(
      el("p", { className: "t-mono", text: context.session_id, attrs: { title: "Идентификатор сессии" } }),
      el("p", {
        className: "t-compact",
        text: health ? `Состояние: ${health.label}` : `Состояние: ${context.health}`,
      }),
    );
    while (recovery.firstChild) recovery.removeChild(recovery.firstChild);
    if (context.health !== "ok" || context.reason_codes.length > 0) {
      recovery.append(
        createRecoveryPanel(context.reason_codes, health ? health.label : context.health),
      );
    }
    while (fieldsHost.firstChild) fieldsHost.removeChild(fieldsHost.firstChild);
    fieldsHost.append(createFieldsTable(context.fields));
    while (userFieldsHost.firstChild) userFieldsHost.removeChild(userFieldsHost.firstChild);
    for (const [key, value] of Object.entries(userEditableFields(context))) {
      const input = document.createElement("input");
      input.type = "text";
      input.className = "ctl";
      input.value = value;
      input.setAttribute("data-field", key);
      userFieldsHost.append(v6Field(key, input));
    }
    notesArea.value = context.notes ?? "";
    tagsInput.value = context.tags.join(", ");
    saveButton.disabled = false;
    renderConflict();
  }

  loader.subscribe((state) => {
    if (state.kind === "ready") {
      renderReady(state.value);
    } else if (state.kind === "loading") {
      saveButton.disabled = true;
      setError("");
    } else if (state.kind === "error") {
      saveButton.disabled = true;
      setError(`${state.error.message} Выберите другую сессию или повторите.`);
    }
  });

  saveMutation.subscribe((state) => {
    saveButton.disabled = state.kind === "pending";
    saveButton.textContent = state.kind === "pending" ? "Сохранение…" : "Сохранить";
  });

  const root = el("section", { className: "panel lnt-cat-inspector" }, [
    el("div", { className: "panel-hd" }, [
      el("h2", { className: "panel-title", text: "Инспектор контекста" }),
    ]),
    el("div", { className: "panel-bd" }, [
      summary,
      recovery,
      fieldsHost,
      el("div", { className: "form-grid" }, [
        v6Field("Заметки", notesArea),
        v6Field("Теги", tagsInput, "Через запятую, например: самошум, стенд-А"),
      ]),
      userFieldsHost,
      conflictPanel,
      errorNote,
      el("div", { className: "form-actions" }, [saveButton]),
    ]),
  ]);

  return {
    root,
    loadSession: async (sessionId) => {
      currentSessionId = sessionId;
      conflict = null;
      renderConflict();
      await loader.load(sessionId);
    },
  };
}
