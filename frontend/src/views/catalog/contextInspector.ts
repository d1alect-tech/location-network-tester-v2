/** Инспектор контекста сессии: поля с источником/доступностью, правка заметок,
 * тегов и пользовательских полей, сохранение через PUT с оптимистичной
 * блокировкой. Конфликт revision показывается как типизированное состояние
 * с потоком «перечитать и объединить» — чужие правки не затираются молча. */

import type { LntApiClient } from "../../api/client";
import type { ContextResponse, ContextUpdateRequest } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";
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

  const title = el("h3", { className: "lnt-cat-inspector-title", text: "Инспектор контекста" });
  const summary = el("div", { className: "lnt-cat-session-summary" });
  const recovery = el("div", {});
  const fieldsHost = el("div", {});
  const notesArea = document.createElement("textarea");
  notesArea.className = "lnt-input lnt-cat-notes";
  notesArea.rows = 4;
  const tagsInput = document.createElement("input");
  tagsInput.type = "text";
  tagsInput.className = "lnt-input";
  const userFieldsHost = el("div", {});
  const conflictPanel = el("div", { className: "lnt-cat-conflict" });
  const errorNote = el("p", { className: "lnt-error-text", attrs: { role: "alert" } });
  const saveButton = el("button", {
    className: "lnt-btn lnt-btn-primary",
    text: "Сохранить",
    attrs: { type: "button" },
  });

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
    errorNote.textContent = "";
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
        errorNote.textContent =
          error instanceof Error ? error.message : "Не удалось сохранить изменения.";
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
      el("p", { className: "lnt-cat-conflict-title", text: conflict.message }),
      buildMergeButton(),
      buildDiscardButton(),
    );
  }

  function buildMergeButton(): HTMLElement {
    const button = el("button", {
      className: "lnt-btn lnt-btn-primary",
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
          errorNote.textContent =
            retryError instanceof Error ? retryError.message : "Повторное сохранение не удалось.";
        }
      })();
    });
    return button;
  }

  function buildDiscardButton(): HTMLElement {
    const button = el("button", {
      className: "lnt-btn",
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
      el("p", { className: "lnt-mono lnt-cat-session-id", text: context.session_id }),
      health
        ? el("p", { text: `Состояние: ${health.label}` })
        : el("p", { text: `Состояние: ${context.health}` }),
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
      input.className = "lnt-input";
      input.value = value;
      input.setAttribute("data-field", key);
      userFieldsHost.append(createField({ label: key, control: input }).root);
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
      errorNote.textContent = "";
    } else if (state.kind === "error") {
      saveButton.disabled = true;
      errorNote.textContent = `${state.error.message} Выберите другую сессию или повторите.`;
    }
  });

  saveMutation.subscribe((state) => {
    saveButton.disabled = state.kind === "pending";
    saveButton.textContent = state.kind === "pending" ? "Сохранение…" : "Сохранить";
  });

  const root = el("section", { className: "lnt-cat-inspector" }, [
    title,
    summary,
    recovery,
    fieldsHost,
    el("div", { className: "lnt-cat-editors" }, [
      createField({ label: "Заметки", control: notesArea }).root,
      createField({
        label: "Теги",
        control: tagsInput,
        hintText: "Через запятую, например: самошум, стенд-А",
      }).root,
      userFieldsHost,
    ]),
    conflictPanel,
    errorNote,
    saveButton,
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
