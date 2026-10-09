/** Панель конфликта revision инспектора: баннер .banner-inline.banner-warn
 * с потоком «перечитать и объединить» / «отбросить мои правки». Выделено из
 * contextInspector ради потолка 250 чистых LOC; состояние конфликта живёт
 * здесь, инспектор передаёт черновик и перезагрузку зависимостями. */

import type { ApiError } from "../../api/errors";
import type { ContextResponse, ContextUpdateRequest } from "../../api/types";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import {
  type RevisionConflict,
  loadConflictMessage,
  mergeDraftOntoFresh,
} from "./inspectorConflict";

export interface ConflictDraft {
  notes: string;
  tags: string[];
  userFields: Record<string, string>;
}

export interface ConflictPanelDeps {
  collectDraft(): ConflictDraft;
  reloadCurrent(): Promise<ContextResponse | null>;
  save(request: ContextUpdateRequest): Promise<unknown>;
  onError(message: string): void;
}

export interface ConflictPanelHandle {
  panel: HTMLElement;
  setConflict(conflict: RevisionConflict | null): void;
  /** 409 на чтении контекста: баннер виден, слияние не предлагается. */
  setLoadError(error: ApiError | null): void;
}

export function createConflictPanel(deps: ConflictPanelDeps): ConflictPanelHandle {
  const panel = el("div", { className: "banner banner-inline banner-warn lnt-cat-conflict" });
  panel.hidden = true;
  let conflict: RevisionConflict | null = null;
  let loadError: ApiError | null = null;

  function render(): void {
    clearElement(panel);
    if (conflict !== null) {
      panel.hidden = false;
      panel.append(
        el("p", { className: "banner-msg", text: conflict.message }),
        buildMergeButton(),
        buildDiscardButton(),
      );
      return;
    }
    if (loadError !== null) {
      panel.hidden = false;
      panel.append(
        el("p", { className: "banner-msg", text: loadConflictMessage(loadError) }),
        buildRetryButton(),
      );
      return;
    }
    panel.hidden = true;
  }

  /** Повтор чтения: баннер уходит только когда сервер реально отдал контекст. */
  function buildRetryButton(): HTMLElement {
    const button = el("button", {
      className: "btn",
      text: "Повторить загрузку",
      attrs: { type: "button" },
    });
    button.addEventListener("click", () => {
      void deps.reloadCurrent().then((fresh) => {
        if (fresh === null) return;
        loadError = null;
        render();
      });
    });
    return button;
  }

  function buildMergeButton(): HTMLElement {
    const button = el("button", {
      className: "btn",
      text: "Перечитать и объединить",
      attrs: { type: "button" },
    });
    button.addEventListener("click", () => {
      void (async () => {
        // Черновик фиксируется ДО перечитывания: рендер формы иначе затрёт
        // поля свежими данными, и объединение потеряло бы правки.
        const draft = deps.collectDraft();
        const fresh = await deps.reloadCurrent();
        if (fresh === null) return;
        try {
          await deps.save(mergeDraftOntoFresh(fresh, draft));
          conflict = null;
          render();
          await deps.reloadCurrent();
          announcePolite("Изменения применены поверх актуальной версии");
        } catch (retryError) {
          deps.onError(
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
      render();
      void deps.reloadCurrent();
    });
    return button;
  }

  return {
    panel,
    setConflict: (next) => {
      conflict = next;
      // Новая сессия сбрасывает и конфликт записи, и отказ чтения.
      if (next === null) loadError = null;
      render();
    },
    setLoadError: (next) => {
      loadError = next;
      render();
    },
  };
}
