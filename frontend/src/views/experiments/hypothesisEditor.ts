/** Редактор гипотез: форма создания/правки и отправка (T11: выделено из
 * hypothesisView). Состояние списка и контекст связей остаются во
 * HypothesisView и приходят аргументами; после сохранения владелец
 * обновляется через onSaved. Без смены поведения и текстов.
 * C1: примитивы формы — в hypothesisForm, сборка payload — в
 * hypothesisPayload; здесь только разметка редактора и отправка. */

import type { LntApiClient } from "../../api/client";
import type { HypothesisRecord } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { clearEditor, selectInput, textInput } from "./hypothesisForm";
import type { HypothesisPayloadInput } from "./hypothesisPayload";
import { buildHypothesisPayload, full } from "./hypothesisPayload";
import {
  type HypothesisDraftInput,
  type HypothesisStatusValue,
  STATUS_LABELS_RU,
  nextStatuses,
} from "./hypothesisState";

export interface HypothesisLinkContext {
  experimentId: string;
  estimand: string;
}

export interface HypothesisEditorDeps {
  client: Pick<LntApiClient, "research">;
  linkContext: HypothesisLinkContext | null;
  onSaved: () => Promise<void>;
}

function infoLineFor(record: HypothesisRecord | null, link: HypothesisLinkContext | null): string {
  if (record === null) {
    return link === null
      ? "Связь с экспериментом не задана — откройте гипотезы из контекста эксперимента."
      : `Связь: ${link.experimentId} · ${link.estimand}`;
  }
  const enriched = full(record);
  return `Доказательства: ${(enriched.evidence_for ?? []).length} за · ${(enriched.evidence_against ?? []).length} против. Связи: ${(enriched.linked_estimands ?? []).map((e) => `${e.experiment_id}·${e.estimand}`).join("; ") || "нет"}`;
}

export function renderHypothesisEditor(
  host: HTMLElement,
  deps: HypothesisEditorDeps,
  record: HypothesisRecord | null,
): void {
  clearEditor(host);
  const statement = textInput("Формулировка утверждения", record?.statement ?? "");
  const mechanism = textInput("Механизм (как это может проявляться)", record?.mechanism ?? "");
  const direction = selectInput({
    labelText: "Ожидаемое направление",
    options: [
      ["increase", "рост"],
      ["decrease", "спад"],
      ["no_direction", "без направления"],
    ],
    selected: (record?.expected_direction as string | undefined) ?? "no_direction",
  });
  const statusSelect = selectInput({
    labelText: "Статус",
    options: nextStatuses((record?.status as HypothesisStatusValue) ?? "draft").map((value) => [
      value,
      STATUS_LABELS_RU[value],
    ]),
    disabled: record === null,
  });

  const form = el("form", { className: "lnt-exp-hypothesis-form" });
  form.append(statement.wrap, mechanism.wrap, direction.wrap);
  if (record !== null) form.append(statusSelect.wrap);
  form.append(
    el("p", { className: "lnt-exp-meta-line", text: infoLineFor(record, deps.linkContext) }),
  );

  const errorLine = el("p", {
    className: "lnt-error-text banner banner-inline",
    attrs: { role: "alert" },
  });
  const submit = el("button", {
    className: "lnt-btn lnt-btn-primary btn",
    text: record === null ? "Создать" : "Сохранить",
    attrs: { type: "submit" },
  });
  const cancelButton = el("button", {
    className: "lnt-btn btn-secondary",
    text: "Закрыть",
    attrs: { type: "button" },
  });
  cancelButton.addEventListener("click", () => clearEditor(host));
  form.append(
    el("div", { className: "lnt-exp-actions form-actions cmd-actions" }, [submit, cancelButton]),
    errorLine,
  );

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitHypothesis(deps, host, {
      record,
      values: {
        statementText: statement.input.value,
        mechanismText: mechanism.input.value,
        direction: direction.input.value as HypothesisDraftInput["expectedDirection"],
        nextStatus: statusSelect.input.value as HypothesisStatusValue | "",
        link: deps.linkContext,
      },
      errorLine,
    });
  });

  host.append(
    el("h3", {
      className: "lnt-exp-subtitle",
      text: record === null ? "Новая гипотеза" : `Гипотеза ${record.hypothesis_id}`,
    }),
    form,
  );
  statement.input.focus();
}

interface HypothesisSubmitInput {
  record: HypothesisRecord | null;
  values: HypothesisPayloadInput;
  errorLine: HTMLElement;
}

async function submitHypothesis(
  deps: HypothesisEditorDeps,
  host: HTMLElement,
  input: HypothesisSubmitInput,
): Promise<void> {
  const { record, errorLine } = input;
  const built = buildHypothesisPayload(record, input.values);
  if (!built.ok) {
    errorLine.textContent = built.error;
    return;
  }
  try {
    const saved =
      record === null
        ? await deps.client.research.createHypothesis(built.payload)
        : await deps.client.research.updateHypothesis(record.hypothesis_id, built.payload);
    announcePolite(`Гипотеза сохранена: ${saved.hypothesis_id}`);
    clearEditor(host);
    await deps.onSaved();
  } catch (error) {
    errorLine.textContent = error instanceof Error ? error.message : String(error);
  }
}
