/** Рендер состояний analysis-v2 (G7): вердикт-бейдж шапки, скаляры W1,
 * провалы веток задачи и чипы честного отсутствия панелей. DOM-хелпер el —
 * никакого innerHTML; значения проходят formatScalar продукта. */

import { clearElement, el } from "../../components/primitives/dom";
import { namedBranchNotComputedReason } from "./pairLoadOutcome";
import type { PanelAbsence } from "./panels/host";
import type { ThdVerdict } from "./thdVerdict";
import type { BranchFailure, Scalar } from "./w1Parse";
import { formatScalar } from "./w1Parse";

export const LEGACY_VERDICT = "Analysis v1 legacy (no THD limit check)";
export const VERDICT_HIDDEN = "THD-V: сравнение с лимитом не показано";

function assertNever(value: never): never {
  throw new Error(`unhandled verdict ${String(value)}`);
}

function badge(className: string, text: string, kind: string): HTMLElement {
  return el("span", {
    className: `lnt-w1-badge ${className}`,
    text,
    attrs: { "data-thd-verdict": kind },
  });
}

/** Бейдж вердикта: один на секцию, живёт в шапке (читается без раскрытия). */
export function renderVerdict(host: HTMLElement, verdict: ThdVerdict): void {
  clearElement(host);
  switch (verdict.kind) {
    case "pass":
      host.append(badge("lnt-w1-badge-ok", "THD-V pass", "pass"));
      return;
    case "fail":
      host.append(badge("lnt-w1-badge-fail", "THD-V fail", "fail"));
      return;
    case "legacy":
      host.append(badge("lnt-w1-badge-legacy", LEGACY_VERDICT, "legacy"));
      return;
    case "hidden":
      host.append(badge("lnt-w1-badge-legacy", VERDICT_HIDDEN, "hidden"));
      return;
    default:
      assertNever(verdict);
  }
}

/** Скаляры W1 — плитки ленты анализа (.band-cell): один язык с полосой
 * «Лента анализа», тот же шаг сетки и те же подписи-микрокапсы. */
export function renderScalars(host: HTMLElement, scalars: readonly Scalar[]): void {
  clearElement(host);
  for (const scalar of scalars) {
    host.append(
      el(
        "dl",
        {
          className: "band-cell",
          attrs: { "data-scalar": scalar.key },
        },
        [el("dt", { text: scalar.label }), el("dd", { text: formatScalar(scalar.value) })],
      ),
    );
  }
}

export function renderFailures(host: HTMLElement, failures: readonly BranchFailure[]): void {
  clearElement(host);
  for (const row of failures) {
    host.append(el("li", { text: namedBranchNotComputedReason(row.branch, row.message) }));
  }
}

/** Чип отсутствия: панель не смонтирована — причина названа, а не спрятана. */
export function renderAbsent(host: HTMLElement, rows: readonly PanelAbsence[]): void {
  clearElement(host);
  for (const row of rows) {
    host.append(
      el("li", {
        className: `av2-chip is-${row.tone}`,
        text: `${row.label}: ${row.reason}`,
        attrs: { "data-absent-panel": row.kind, "data-absent-tone": row.tone },
      }),
    );
  }
}
