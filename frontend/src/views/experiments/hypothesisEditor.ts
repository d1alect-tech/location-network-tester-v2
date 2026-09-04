/** Редактор гипотез: форма создания/правки и отправка (T11: выделено из
 * hypothesisView — было 286 чистых LOC). Состояние списка и контекст связей
 * остаются во HypothesisView и приходят аргументами; после сохранения
 * владелец обновляется через onSaved. Без смены поведения и текстов. */

import type { LntApiClient } from "../../api/client";
import type { HypothesisRecord, HypothesisWritePayload } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import {
  type HypothesisDraftInput,
  type HypothesisStatusValue,
  STATUS_LABELS_RU,
  canTransition,
  nextStatuses,
  validateHypothesisDraft,
} from "./hypothesisState";

export interface HypothesisLinkContext {
  experimentId: string;
  estimand: string;
}

/** Открытые поля HypothesisRecord (бэкенд-модель шире клиентского ядра). */
interface HypothesisFull {
  evidence_for?: { result_id: string; result_kind: string }[];
  evidence_against?: { result_id: string; result_kind: string }[];
  linked_estimands?: { experiment_id: string; estimand: string }[];
  confounds?: string[];
  revision_history?: { revision: number; occurred_at: string; actor: string; reason: string }[];
}

function full(record: HypothesisRecord | null): HypothesisFull {
  return (record ?? {}) as unknown as HypothesisFull;
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function clearEditor(host: HTMLElement): void {
  while (host.firstChild) host.removeChild(host.firstChild);
}

function textInput(
  labelText: string,
  value: string,
): { wrap: HTMLElement; input: HTMLInputElement } {
  const input = el("input", { className: "lnt-input ctl", attrs: { type: "text" } });
  input.value = value;
  const label = el("label", { className: "lnt-label field-label", text: labelText });
  label.htmlFor = input.id = `hyp-${labelText.length}-${Math.random().toString(36).slice(2, 7)}`;
  return { wrap: el("div", { className: "lnt-field field" }, [label, input]), input };
}

function selectInput(
  labelText: string,
  options: [string, string][],
  selected?: string,
  disabled = false,
): { wrap: HTMLElement; input: HTMLSelectElement } {
  const select = el("select", { className: "lnt-select ctl" });
  for (const [value, text] of options) {
    const option = el("option", { text, attrs: { value } });
    if (value === selected) option.selected = true;
    select.append(option);
  }
  if (options.length === 0) select.disabled = true;
  if (disabled && options.length === 0) select.disabled = true;
  const label = el("label", { className: "lnt-label field-label", text: labelText });
  label.htmlFor =
    select.id = `hyp-sel-${labelText.length}-${Math.random().toString(36).slice(2, 7)}`;
  return { wrap: el("div", { className: "lnt-field field" }, [label, select]), input: select };
}

export interface HypothesisEditorDeps {
  client: Pick<LntApiClient, "research">;
  linkContext: HypothesisLinkContext | null;
  onSaved: () => Promise<void>;
}

export function renderHypothesisEditor(
  host: HTMLElement,
  deps: HypothesisEditorDeps,
  record: HypothesisRecord | null,
): void {
  clearEditor(host);
  const statement = textInput("Формулировка утверждения", record?.statement ?? "");
  const mechanism = textInput("Механизм (как это может проявляться)", record?.mechanism ?? "");
  const direction = selectInput(
    "Ожидаемое направление",
    [
      ["increase", "рост"],
      ["decrease", "спад"],
      ["no_direction", "без направления"],
    ],
    (record?.expected_direction as string | undefined) ?? "no_direction",
  );
  const statusSelect = selectInput(
    "Статус",
    nextStatuses((record?.status as HypothesisStatusValue) ?? "draft").map((value) => [
      value,
      STATUS_LABELS_RU[value],
    ]),
    undefined,
    record === null,
  );

  const form = el("form", { className: "lnt-exp-hypothesis-form" });
  form.append(statement.wrap, mechanism.wrap, direction.wrap);
  if (record !== null) form.append(statusSelect.wrap);

  const infoLine = el("p", { className: "lnt-exp-meta-line" });
  if (record !== null) {
    const enriched = full(record);
    infoLine.textContent = `Доказательства: ${(enriched.evidence_for ?? []).length} за · ${(enriched.evidence_against ?? []).length} против. Связи: ${(enriched.linked_estimands ?? []).map((e) => `${e.experiment_id}·${e.estimand}`).join("; ") || "нет"}`;
  } else {
    const link = deps.linkContext;
    infoLine.textContent =
      link === null
        ? "Связь с экспериментом не задана — откройте гипотезы из контекста эксперимента."
        : `Связь: ${link.experimentId} · ${link.estimand}`;
  }
  form.append(infoLine);

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
    void submitHypothesis(
      deps,
      host,
      record,
      statement.input.value,
      mechanism.input.value,
      direction.input.value as HypothesisDraftInput["expectedDirection"],
      statusSelect.input.value as HypothesisStatusValue | "",
      errorLine,
    );
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

async function submitHypothesis(
  deps: HypothesisEditorDeps,
  host: HTMLElement,
  record: HypothesisRecord | null,
  statementText: string,
  mechanismText: string,
  direction: HypothesisDraftInput["expectedDirection"],
  nextStatus: HypothesisStatusValue | "",
  errorLine: HTMLElement,
): Promise<void> {
  const link = deps.linkContext;
  const draft: HypothesisDraftInput = {
    hypothesisId:
      record?.hypothesis_id ??
      `h.${nowIso()
        .replaceAll(/[-:.TZ]/gu, "")
        .slice(2, 14)
        .toLowerCase()}.${Math.floor(Date.now() / 1000) % 1000}`,
    statement: statementText,
    mechanism: mechanismText,
    expectedDirection: direction,
    linkedEstimands:
      full(record).linked_estimands ??
      (link ? [{ experiment_id: link.experimentId, estimand: link.estimand }] : []),
    confounds: full(record).confounds ?? [],
    nowIso: nowIso(),
    actor: "user:operator",
  };
  const validation = validateHypothesisDraft(draft);
  if (!validation.ok) {
    errorLine.textContent = Object.values(validation.errors)[0] ?? "Проверьте поля формы.";
    return;
  }
  if (
    record !== null &&
    nextStatus &&
    !canTransition(record.status as HypothesisStatusValue, nextStatus)
  ) {
    errorLine.textContent = `Недопустимый переход статуса: ${record.status} → ${nextStatus}.`;
    return;
  }
  const revisionHistory = full(record).revision_history ?? [
    {
      revision: 1,
      occurred_at: draft.nowIso,
      actor: draft.actor,
      reason: "создана редактором гипотез",
    },
  ];
  const payload: HypothesisWritePayload = {
    hypothesis: {
      schema_version: 1,
      hypothesis_id: draft.hypothesisId,
      revision: record?.revision ?? 1,
      statement: draft.statement.trim(),
      expected_direction: draft.expectedDirection,
      mechanism: draft.mechanism.trim(),
      linked_estimands: draft.linkedEstimands,
      confounds: draft.confounds,
      evidence_for: full(record).evidence_for ?? [],
      evidence_against: full(record).evidence_against ?? [],
      status: nextStatus || (record?.status ?? "draft"),
      revision_history: revisionHistory,
    },
    expected_revision: record?.revision ?? 0,
  };
  try {
    const saved =
      record === null
        ? await deps.client.research.createHypothesis(payload)
        : await deps.client.research.updateHypothesis(record.hypothesis_id, payload);
    announcePolite(`Гипотеза сохранена: ${saved.hypothesis_id}`);
    clearEditor(host);
    await deps.onSaved();
  } catch (error) {
    errorLine.textContent = error instanceof Error ? error.message : String(error);
  }
}
