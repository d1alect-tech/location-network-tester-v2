/** Мастер создания эксперимента (todo 43): пошагово — план (A/B, A/B/A,
 * повторные блоки), выбор сессий по условиям из каталога, метаданные и
 * estimand. Итог — валидный ExperimentWritePayload (schema 1). */

import type { LntApiClient } from "../../api/client";
import type { CatalogSession } from "../../api/types";
import type { ExperimentWritePayload } from "../../api/types-research";
import { type DialogHandle, openDialog } from "../../components/primitives/dialog";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { buildExperimentDraft, protocolLabel, validateDraft } from "./experimentModel";
import type { DraftExperimentInput, ProtocolKind } from "./experimentModel";
import { numberField, selectField, textField } from "./experimentWizardFields";

const PLANS: ("ab" | "aba" | "repeated_blocks")[] = ["ab", "aba", "repeated_blocks"];

function planConditions(kind: ProtocolKind): string[] {
  if (kind === "aba") return ["cond_a1", "cond_b", "cond_a2"];
  if (kind === "ab") return ["cond_a", "cond_b"];
  return ["block_1", "block_2"];
}

export interface WizardOptions {
  client: Pick<LntApiClient, "catalogSessions" | "research">;
  onCreated: (experimentId: string) => void;
}

export class ExperimentWizard {
  readonly root: HTMLElement;
  private readonly client: Pick<LntApiClient, "catalogSessions" | "research">;
  private readonly onCreated: (experimentId: string) => void;
  private kind: ProtocolKind = "aba";
  /** session_id → условие; сессия ровно в одном условии. */
  private assignment = new Map<string, string>();
  private sessions: CatalogSession[] = [];
  private readonly sessionListHost: HTMLElement;
  private dialog: DialogHandle | null = null;
  private closed = false;
  private readonly controller = new AbortController();

  constructor(options: WizardOptions) {
    this.client = options.client;
    this.onCreated = options.onCreated;
    const idInput = textField("Идентификатор эксперимента", "exp.aba.demo");
    const titleInput = textField("Название", "");
    const questionInput = textField("Вопрос исследования", "");
    const estimandInput = textField("Оцениваемый признак (feature key)", "needle_mean_v");
    const minNInput = numberField("Минимальный N единиц", 3);
    const planSelect = selectField(
      "План эксперимента",
      PLANS.map((kind) => [kind, protocolLabel(kind)]),
      "aba",
    );
    const errorLine = el("p", {
      className: "lnt-error-text banner banner-inline",
      attrs: { role: "alert" },
    });
    this.sessionListHost = el("div", { className: "lnt-exp-wizard-sessions" });

    const form = el("form", { className: "lnt-exp-wizard-form" });
    form.append(
      el("div", { className: "form-grid" }, [
        planSelect.wrap,
        idInput.wrap,
        titleInput.wrap,
        questionInput.wrap,
        estimandInput.wrap,
        minNInput.wrap,
      ]),
    );
    form.append(
      el("h3", { className: "lnt-exp-subtitle", text: "Сессии и условия" }),
      this.sessionListHost,
    );
    form.append(errorLine);
    const submit = el("button", {
      className: "lnt-btn lnt-btn-primary btn",
      text: "Создать эксперимент",
      attrs: { type: "submit" },
    });
    form.append(el("div", { className: "form-actions cmd-actions" }, [submit]));

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      errorLine.textContent = "";
      const input: DraftExperimentInput = {
        experimentId: idInput.input.value.trim(),
        title: titleInput.input.value,
        question: questionInput.input.value,
        kind: this.kind,
        sessionsByCondition: this.sessionsByCondition(),
        estimandKey: estimandInput.input.value.trim(),
        units: "V",
        minimumN: Number(minNInput.input.value),
        nowIso: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
        actor: "user:operator",
      };
      const validation = validateDraft(input);
      if (!validation.ok) {
        errorLine.textContent =
          Object.values(validation.errors)[0] ?? "Проверьте поля мастера создания.";
        return;
      }
      const payload: ExperimentWritePayload = {
        experiment: buildExperimentDraft(input),
        expected_revision: 0,
      };
      submit.disabled = true;
      void this.client.research
        .createExperiment(payload, { signal: this.controller.signal })
        .then((created) => {
          if (this.closed) return;
          announcePolite(`Эксперимент создан: ${created.experiment_id}`);
          this.close();
          this.onCreated(created.experiment_id);
        })
        .catch((error: unknown) => {
          if (this.closed) return;
          errorLine.textContent = error instanceof Error ? error.message : String(error);
          submit.disabled = false;
        });
    });

    planSelect.input.addEventListener("change", () => {
      this.kind = planSelect.input.value as ProtocolKind;
      this.renderSessions();
    });

    this.root = el(
      "section",
      {
        className: "lnt-exp-wizard wizard-modal modal",
        attrs: { role: "dialog", "aria-modal": "true", "aria-label": "Новый эксперимент" },
      },
      [
        el("h2", { className: "placeholder-title panel-title", text: "Новый эксперимент" }),
        el("p", {
          className: "lnt-helper-text",
          text: "Мастер создаёт протокол с таймлайном шагов; участники получают условия по вашему назначению.",
        }),
        form,
      ],
    );
    void this.loadSessions();
  }

  open(onClosed: () => void): void {
    if (this.dialog !== null) {
      this.focus();
      return;
    }
    this.root.classList.remove("lnt-exp-wizard", "wizard-modal", "modal");
    this.root.removeAttribute("role");
    this.root.removeAttribute("aria-modal");
    this.root.removeAttribute("aria-label");
    this.root.querySelector(".placeholder-title")?.remove();
    const dialog = openDialog({ title: "Новый эксперимент", content: this.root });
    const primitiveClose = dialog.close;
    dialog.close = () => {
      if (this.closed) return;
      this.closed = true;
      this.controller.abort();
      this.dialog = null;
      onClosed();
      primitiveClose();
    };
    this.dialog = dialog;
    const box = dialog.root.querySelector<HTMLElement>('[role="dialog"]');
    box?.classList.add("lnt-exp-wizard", "wizard-modal", "modal");
  }

  focus(): void {
    this.dialog?.root.querySelector<HTMLElement>("input, select, button")?.focus();
  }

  close(): void {
    this.dialog?.close();
  }

  private async loadSessions(): Promise<void> {
    try {
      const page = await this.client.catalogSessions(
        { page_size: 50 },
        { signal: this.controller.signal },
      );
      if (this.closed) return;
      this.sessions = page.items;
      this.renderSessions();
    } catch {
      if (this.closed) return;
      this.sessionListHost.replaceChildren(
        el("p", { className: "lnt-helper-text", text: "Каталог сессий недоступен." }),
      );
    }
  }

  private sessionsByCondition(): Record<string, { session_id: string; storage_ref: string }[]> {
    const result: Record<string, { session_id: string; storage_ref: string }[]> = {};
    for (const conditionId of planConditions(this.kind)) result[conditionId] = [];
    for (const [sessionId, conditionId] of this.assignment) {
      const session = this.sessions.find((item) => item.id === sessionId);
      if (!session) continue;
      result[conditionId]?.push({ session_id: sessionId, storage_ref: `/sessions/${sessionId}` });
    }
    return result;
  }

  private renderSessions(): void {
    while (this.sessionListHost.firstChild)
      this.sessionListHost.removeChild(this.sessionListHost.firstChild);
    const conditions = planConditions(this.kind);
    if (this.sessions.length === 0) {
      this.sessionListHost.append(
        el("p", { className: "lnt-helper-text", text: "Нет сессий в каталоге." }),
      );
      return;
    }
    for (const session of this.sessions) {
      const select = el("select", {
        className: "lnt-select ctl",
        attrs: { "aria-label": `Условие сессии ${session.id}` },
      });
      select.append(el("option", { text: "— не участвует —", attrs: { value: "" } }));
      for (const conditionId of conditions) {
        select.append(el("option", { text: conditionId, attrs: { value: conditionId } }));
      }
      const assigned = this.assignment.get(session.id) ?? "";
      select.value = conditions.includes(assigned) ? assigned : "";
      select.addEventListener("change", () => {
        if (select.value === "") this.assignment.delete(session.id);
        else this.assignment.set(session.id, select.value);
      });
      this.sessionListHost.append(
        el("div", { className: "lnt-field-inline field" }, [
          el("span", {
            className: "lnt-label-text field-label",
            text: session.label === null ? session.id : `${session.id} · ${session.label}`,
          }),
          select,
        ]),
      );
    }
  }
}
