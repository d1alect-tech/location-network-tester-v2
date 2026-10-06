/** Инспектор контекста сессии V6 по варианту «Плотный список»: сводка
 * плитками, здоровье контекста с ревизией, баннер восстановления, блок
 * THD-V (факт + сравнение с пределом), секция полей с источником, теги,
 * правка заметок/тегов/пользовательских полей и сохранение через PUT
 * с оптимистичной блокировкой. Повреждённый контекст не перезаписывается:
 * сохранение отклоняется строкой role=alert с кодами причин. Конфликт
 * revision — в inspectorConflictPanel, рендеры — contextSummary/contextThd,
 * метрики — contextMetrics. Хук .lnt-cat-inspector и связки e2e
 * (.lnt-cat-session-summary, .lnt-cat-notes, .lnt-btn-primary) сохранены. */

import type { LntApiClient } from "../../api/client";
import type { ContextResponse, ContextUpdateRequest } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { createMutation, createResourceLoader } from "../../state/resource";
import { v6Field } from "./catalogV6Field";
import { createFieldsSection, createRecoveryPanel } from "./contextFieldsView";
import { EMPTY_METRICS, type SessionMetrics, readSessionMetrics } from "./contextMetrics";
import {
  type SessionMeta,
  renderHealthRow,
  renderReadouts,
  renderTagsSection,
} from "./contextSummary";
import { renderThdBlock } from "./contextThd";
import {
  type RevisionConflict,
  conflictFromError,
  isRevisionConflict,
  mergeDraftOntoFresh,
  userEditableFields,
} from "./inspectorConflict";
import { type ConflictDraft, createConflictPanel } from "./inspectorConflictPanel";

export interface ContextInspectorOptions {
  client: LntApiClient;
}

export interface ContextInspectorHandle {
  root: HTMLElement;
  loadSession(sessionId: string, meta?: SessionMeta): Promise<void>;
}

export function createContextInspector(options: ContextInspectorOptions): ContextInspectorHandle {
  const { client } = options;
  let currentSessionId: string | null = null;
  let meta: SessionMeta | null = null;
  let metrics: SessionMetrics = EMPTY_METRICS;
  let animateNext = false;
  let currentBody: HTMLElement | null = null;

  const loader = createResourceLoader<ContextResponse>((key, signal) =>
    client.context(key, { signal }),
  );
  const saveMutation = createMutation<ContextUpdateRequest, ContextResponse>((request) => {
    if (currentSessionId === null) return Promise.reject(new Error("сессия не выбрана"));
    return client.updateContext(currentSessionId, request);
  });

  const bodyHost = el("div", { className: "insp-host-body" });
  const notesArea = document.createElement("textarea");
  notesArea.className = "ctl lnt-cat-notes";
  notesArea.rows = 4;
  const tagsInput = document.createElement("input");
  tagsInput.type = "text";
  tagsInput.className = "ctl";
  const userFieldsHost = el("div", { className: "form-grid" });
  // Пустая строка ошибки остаётся скрытой: пустой role=alert и красная рамка
  // до первой загрузки/сохранения — ложный сигнал (см. contextInspector.test.ts).
  const errorNote = el("p", {
    className: "lnt-error-text banner banner-inline",
    attrs: { role: "alert" },
  });
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

  async function saveRequest(request: ContextUpdateRequest): Promise<unknown> {
    await client.ensureReady();
    return saveMutation.run(request);
  }

  async function reloadCurrent(): Promise<ContextResponse | null> {
    if (currentSessionId === null) return null;
    await loader.load(currentSessionId);
    const state = loader.get();
    return state.kind === "ready" ? state.value : null;
  }

  function collectDraft(): ConflictDraft {
    const userFields: Record<string, string> = {};
    for (const input of userFieldsHost.querySelectorAll<HTMLInputElement>("input[data-field]")) {
      const key = input.getAttribute("data-field");
      if (key !== null) userFields[key] = input.value;
    }
    const tags = tagsInput.value
      .split(",")
      .map((part) => part.trim())
      .filter((part) => part !== "");
    return { notes: notesArea.value, tags, userFields };
  }

  const conflictUi = createConflictPanel({
    collectDraft,
    reloadCurrent,
    save: saveRequest,
    onError: setError,
  });

  function buildRequest(context: ContextResponse): ContextUpdateRequest {
    const draft = collectDraft();
    return {
      expected_revision: context.revision,
      fields: mergeDraftOntoFresh(context, draft).fields,
      tags: draft.tags,
      notes: draft.notes,
    };
  }

  function refusalMessage(context: ContextResponse): string {
    const reasons = context.reason_codes.length > 0 ? ` ${context.reason_codes.join("; ")}.` : "";
    return `Сохранение отклонено: контекст повреждён.${reasons} Сначала восстановите context.json.`;
  }

  async function runSave(): Promise<void> {
    const state = loader.get();
    if (state.kind !== "ready") return;
    setError("");
    if (state.value.health === "context_invalid") {
      setError(refusalMessage(state.value));
      announcePolite("Сохранение отклонено: контекст повреждён");
      return;
    }
    try {
      await saveRequest(buildRequest(state.value));
      conflictUi.setConflict(null);
      await reloadCurrent();
      announcePolite("Контекст сохранён");
    } catch (error) {
      if (isRevisionConflict(error)) {
        const conflict: RevisionConflict = conflictFromError(state.value.revision, error);
        conflictUi.setConflict(conflict);
        announcePolite("Конфликт версий: контекст изменён другим процессом");
      } else {
        setError(error instanceof Error ? error.message : "Не удалось сохранить изменения.");
      }
    }
  }

  saveButton.addEventListener("click", () => void runSave());

  function renderBody(animate: boolean): void {
    while (bodyHost.firstChild) bodyHost.removeChild(bodyHost.firstChild);
    currentBody = null;
    const state = loader.get();
    if (state.kind !== "ready" || meta === null) {
      bodyHost.append(
        el("p", {
          className: "insp-none",
          text: "Сессия не выбрана. Выберите строку в каталоге слева.",
        }),
      );
      return;
    }
    const context = state.value;
    const body = el("div", { className: animate ? "insp-body insp-enter" : "insp-body" });
    body.append(
      renderReadouts(meta, metrics),
      renderHealthRow(context.health, context.revision, meta),
    );
    if (context.health !== "context_valid" || context.reason_codes.length > 0) {
      body.append(createRecoveryPanel(context.reason_codes, context.health));
    }
    body.append(
      renderThdBlock(metrics),
      createFieldsSection(context),
      renderTagsSection(context.tags),
    );
    bodyHost.append(body);
    currentBody = body;
    notesArea.value = context.notes ?? "";
    tagsInput.value = context.tags.join(", ");
    while (userFieldsHost.firstChild) userFieldsHost.removeChild(userFieldsHost.firstChild);
    for (const [key, value] of Object.entries(userEditableFields(context))) {
      const input = document.createElement("input");
      input.type = "text";
      input.className = "ctl";
      input.value = value;
      input.setAttribute("data-field", key);
      userFieldsHost.append(v6Field(key, input));
    }
    saveButton.disabled = false;
  }

  /** Метрики догрузились после входа: плитки и блок THD меняются точечно,
   * анимация входа и фокус формы не сбрасываются. */
  function refreshMetrics(): void {
    if (currentBody === null || meta === null) return;
    currentBody.querySelector(".readout-grid")?.replaceWith(renderReadouts(meta, metrics));
    currentBody.querySelector(".insp-thd")?.replaceWith(renderThdBlock(metrics));
  }

  loader.subscribe((state) => {
    if (state.kind === "ready") {
      renderBody(animateNext);
      animateNext = false;
    } else if (state.kind === "loading") {
      saveButton.disabled = true;
      setError("");
    } else if (state.kind === "error") {
      saveButton.disabled = true;
      renderBody(false);
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
      bodyHost,
      el("div", { className: "form-grid" }, [
        v6Field("Заметки", notesArea, "Описание замера, условия, что проверить"),
        v6Field("Теги", tagsInput, "Через запятую, например: самошум, стенд-А"),
      ]),
      userFieldsHost,
      conflictUi.panel,
      errorNote,
      el("div", { className: "form-actions" }, [
        saveButton,
        el("span", {
          className: "form-note",
          text: "Сохранение повышает ревизию контекста; черновик заметок и тегов применяется к сессии.",
        }),
      ]),
    ]),
  ]);

  return {
    root,
    loadSession: async (sessionId, nextMeta) => {
      currentSessionId = sessionId;
      if (nextMeta) meta = nextMeta;
      if (meta === null) meta = { id: sessionId, createdUtc: null, sessionHealth: "" };
      metrics = EMPTY_METRICS;
      animateNext = true;
      conflictUi.setConflict(null);
      const detail = client.plots.detail(sessionId).catch(() => null);
      await loader.load(sessionId);
      const payload = await detail;
      if (currentSessionId !== sessionId) return;
      metrics = readSessionMetrics(payload);
      refreshMetrics();
    },
  };
}
