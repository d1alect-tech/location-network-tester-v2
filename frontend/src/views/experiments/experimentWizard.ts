/** Мастер создания эксперимента (todo 43): пошагово — план (A/B, A/B/A,
 * повторные блоки), выбор сессий по условиям из каталога, метаданные и
 * estimand. Итог — валидный ExperimentWritePayload (schema 1). */

import type { LntApiClient } from "../../api/client";
import type { CatalogSession } from "../../api/types";
import type { ExperimentWritePayload } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { buildExperimentDraft, protocolLabel, validateDraft } from "./experimentModel";
import type { DraftExperimentInput, ProtocolKind } from "./experimentModel";

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
  private onCreated: (experimentId: string) => void;
  private kind: ProtocolKind = "aba";
  /** session_id → условие; сессия ровно в одном условии. */
  private assignment = new Map<string, string>();
  private sessions: CatalogSession[] = [];
  private sessionListHost: HTMLElement;

  constructor(options: WizardOptions) {
    this.client = options.client;
    this.onCreated = options.onCreated;
    const idInput = text("Идентификатор эксперимента", "exp.aba.demo");
    const titleInput = text("Название", "");
    const questionInput = text("Вопрос исследования", "");
    const estimandInput = text("Оцениваемый признак (feature key)", "band_mid_total");
    const unitsInput = text("Единицы измерения", "В²/Гц");
    const minNInput = numberInput("Минимальный N единиц", 3);
    const planSelect = select(
      "План эксперимента",
      PLANS.map((kind) => [kind, protocolLabel(kind)]),
      "aba",
    );
    const errorLine = el("p", { className: "lnt-error-text", attrs: { role: "alert" } });
    this.sessionListHost = el("div", { className: "lnt-exp-wizard-sessions" });

    const form = el("form", { className: "lnt-exp-wizard-form" });
    form.append(
      planSelect.wrap,
      idInput.wrap,
      titleInput.wrap,
      questionInput.wrap,
      estimandInput.wrap,
      unitsInput.wrap,
      minNInput.wrap,
    );
    form.append(
      el("h3", { className: "lnt-exp-subtitle", text: "Сессии и условия" }),
      this.sessionListHost,
    );
    form.append(errorLine);
    const submit = el("button", {
      className: "lnt-btn lnt-btn-primary",
      text: "Создать эксперимент",
      attrs: { type: "submit" },
    });
    form.append(submit);

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
        units: unitsInput.input.value.trim() || "у.е.",
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
        .createExperiment(payload)
        .then((created) => {
          announcePolite(`Эксперимент создан: ${created.experiment_id}`);
          this.onCreated(created.experiment_id);
          this.root.remove();
        })
        .catch((error: unknown) => {
          errorLine.textContent = error instanceof Error ? error.message : String(error);
          submit.disabled = false;
        });
    });

    planSelect.input.addEventListener("change", () => {
      this.kind = planSelect.input.value as ProtocolKind;
      this.renderSessions();
    });

    this.root = el("section", { className: "lnt-exp-wizard" }, [
      el("h2", { className: "placeholder-title", text: "Новый эксперимент" }),
      el("p", {
        className: "lnt-helper-text",
        text: "Мастер создаёт протокол с таймлайном шагов; участники получают условия по вашему назначению.",
      }),
      form,
    ]);
    void this.loadSessions();
  }

  private async loadSessions(): Promise<void> {
    try {
      const page = await this.client.catalogSessions({ page_size: 50 });
      this.sessions = page.items;
      this.renderSessions();
    } catch {
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
        className: "lnt-select",
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
        el("div", { className: "lnt-field-inline" }, [
          el("span", {
            className: "lnt-label-text",
            text: session.label === null ? session.id : `${session.id} · ${session.label}`,
          }),
          select,
        ]),
      );
    }
  }
}

function text(labelText: string, value: string): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = el("input", { className: "lnt-input", attrs: { type: "text" } });
  input.value = value;
  const label = el("label", { className: "lnt-label", text: labelText });
  label.htmlFor = input.id = `wiz-${labelText.replace(/\s+/gu, "-").toLowerCase()}`;
  return { wrap: el("div", { className: "lnt-field" }, [label, input]), input };
}

function numberInput(
  labelText: string,
  value: number,
): { wrap: HTMLElement; input: HTMLInputElement } {
  const built = text(labelText, String(value));
  built.input.setAttribute("type", "number");
  built.input.min = "2";
  return built;
}

function select(
  labelText: string,
  options: [string, string][],
  selected?: string,
): { wrap: HTMLElement; input: HTMLSelectElement } {
  const selectEl = el("select", { className: "lnt-select" });
  for (const [value, optionText] of options) {
    const option = el("option", { text: optionText, attrs: { value } });
    if (value === selected) option.selected = true;
    selectEl.append(option);
  }
  const label = el("label", { className: "lnt-label", text: labelText });
  label.htmlFor = selectEl.id = ` wiz-${labelText.replace(/\s+/g, "-").toLowerCase()}`.trimStart();
  return { wrap: el("div", { className: "lnt-field" }, [label, selectEl]), input: selectEl };
}
