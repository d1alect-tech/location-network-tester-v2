/** Таблица участников с QC и явными исключениями (todo 43).
 * Исключённые участники НИКОГДА не скрываются: зачёркивание + текст причины.
 * Кнопка «Отменить» добавляет компенсирующую revision (аудит виден).
 * Верdictы QC — глиф + текст, не только цвет (a11y). */

import type { OpenRecord } from "../../api/types-research";
import { el } from "../../components/primitives/dom";
import { errorWithRetry } from "../../components/primitives/stateViews";
import { announcePolite } from "../../components/primitives/status";
import type { ExperimentsStore } from "./experimentsStore";
import { currentState, deriveQcVerdict } from "./memberQc";
import type { MemberInclusion, QcVerdict } from "./memberQc";

export interface MemberRow {
  readonly sessionId: string;
  readonly role: string;
  readonly conditionId: string;
  readonly order: number;
  readonly health: string;
  readonly verdict: QcVerdict;
  readonly inclusion: MemberInclusion;
}

const GLYPHS = { ok: "●", warn: "▲", error: "✕" } as const;

export interface MemberTableOptions {
  store: ExperimentsStore;
  experimentId: string;
  /** health каталога по session_id; отсутствие записи — «недоступно». */
  healthBySession: Map<string, string>;
  onInclusionChange?: () => void;
}

function rowOf(options: MemberTableOptions, raw: OpenRecord): MemberRow | null {
  const sessionId = typeof raw.session_id === "string" ? raw.session_id : null;
  const role = typeof raw.role === "string" ? raw.role : "?";
  const conditionId = typeof raw.condition_id === "string" ? raw.condition_id : "?";
  const order = typeof raw.order === "number" ? raw.order : Number.NaN;
  if (sessionId === null) return null;
  const health = options.healthBySession.get(sessionId) ?? "health_unavailable";
  return {
    sessionId,
    role,
    conditionId,
    order,
    health,
    verdict: deriveQcVerdict(health),
    inclusion: options.store.inclusion(options.experimentId, sessionId),
  };
}

function auditLines(inclusion: MemberInclusion): string[] {
  const labels: Record<string, string> = {
    proposed: "предложен",
    included: "включён",
    excluded: "исключён",
  };
  return inclusion.history.map((revision) => {
    const undo =
      revision.undo_of_revision !== null
        ? ` (отмена ревизии ${String(revision.undo_of_revision)})`
        : "";
    return `Ревизия ${String(revision.revision)}: ${labels[revision.state] ?? revision.state}, причина: ${revision.reason}${undo} · ${revision.actor}`;
  });
}

export class MemberTableView {
  readonly root: HTMLElement;
  private options: MemberTableOptions;
  private rows: MemberRow[] = [];
  private body: HTMLElement;
  private readonly outageHost: HTMLElement;

  constructor(options: MemberTableOptions) {
    this.options = options;
    this.body = el("div", {});
    this.outageHost = el("div", { className: "lnt-exp-health-outage", attrs: { hidden: "" } });
    this.root = el("section", { className: "lnt-exp-members" }, [
      el("h3", { className: "lnt-exp-subtitle", text: "Участники, QC и исключения" }),
      el("p", {
        className: "lnt-helper-text",
        text: "Исключённые участники остаются в таблице (зачёркнуты) с причиной; «Отменить» добавляет компенсирующую запись аудита.",
      }),
      this.outageHost,
      this.body,
    ]);
  }

  /** Outage-баннер здоровья (role=alert + повтор) вместо выдуманных вердиктов. */
  showHealthOutage(message: string, onRetry: () => void): void {
    this.outageHost.replaceChildren(errorWithRetry(message, onRetry, "Повторить"));
    this.outageHost.removeAttribute("hidden");
  }

  /** Убирает outage-баннер после успешной загрузки здоровья. */
  clearHealthOutage(): void {
    this.outageHost.replaceChildren();
    this.outageHost.setAttribute("hidden", "");
  }

  /** Обновляет контекст при загрузке другого эксперимента. */
  setContext(options: { experimentId: string; healthBySession: Map<string, string> }): void {
    this.options = { ...this.options, ...options };
    this.rows = this.rows.map((row) => ({
      ...row,
      verdict: deriveQcVerdict(
        this.options.healthBySession.get(row.sessionId) ?? "health_unavailable",
      ),
      inclusion: this.options.store.inclusion(this.options.experimentId, row.sessionId),
    }));
  }

  setMembers(members: readonly OpenRecord[]): void {
    this.rows = members
      .map((raw) => rowOf(this.options, raw))
      .filter((row): row is MemberRow => row !== null);
    this.render();
  }

  /** Строки с актуальными verdict/inclusion — для сравнения и трендов. */
  getRows(): MemberRow[] {
    return this.rows.map((row) => ({
      ...row,
      inclusion: this.options.store.inclusion(this.options.experimentId, row.sessionId),
    }));
  }

  private render(): void {
    const table = el("table", { className: "lnt-table lnt-exp-member-table tbl tbl-tight" });
    const thead = el("thead");
    const headRow = el("tr");
    for (const header of ["Сессия", "Условие", "Порядок", "QC-вердикт", "Состояние", "Действия"]) {
      headRow.append(el("th", { attrs: { scope: "col" }, text: header }));
    }
    thead.append(headRow);
    const tbody = el("tbody");
    for (const row of this.rows) {
      tbody.append(this.rowElement(row));
    }
    table.append(thead, tbody);
    const wrap = el("div", { className: "tbl-wrap" }, [table]);
    this.body.replaceChildren(wrap);
  }

  private rowElement(row: MemberRow): HTMLElement {
    // Включённость читается из магазина на каждый рендер: кэш строк устарает
    // сразу после исключения/отмены.
    const inclusion = this.options.store.inclusion(this.options.experimentId, row.sessionId);
    const tr = el("tr", { className: "lnt-exp-member-row" });
    if (currentState(inclusion) === "excluded") tr.classList.add("lnt-exp-excluded");

    const sessionCell = el("td", { text: row.sessionId });
    const conditionCell = el("td", { text: row.conditionId });
    const orderCell = el("td", { text: String(row.order) });

    const glyph = el("span", {
      className: `lnt-status-glyph glyph glyph-${row.verdict.tone === "error" ? "err" : row.verdict.tone}`,
      text: GLYPHS[row.verdict.tone],
      attrs: { "aria-hidden": "true" },
    });
    const verdictPill = el(
      "span",
      { className: `lnt-status-pill lnt-tone-${row.verdict.tone} glyph` },
      [glyph],
    );
    verdictPill.append(
      document.createTextNode(
        `${row.verdict.label}${row.verdict.reason_code === null ? "" : ` (${row.verdict.reason_code})`}`,
      ),
    );
    const verdictCell = el("td");
    verdictCell.append(verdictPill);

    const stateText =
      currentState(inclusion) === "excluded"
        ? `Исключён: ${inclusion.history[inclusion.history.length - 1]?.reason ?? "—"}`
        : currentState(inclusion) === "included"
          ? "Включён в сравнение"
          : "Предложен";
    const stateCell = el("td", { text: stateText });

    const actions = el("td");
    const detailsButton = el("button", {
      className: "lnt-btn lnt-btn-small btn-quiet",
      text: "Аудит",
    });
    detailsButton.addEventListener("click", () => this.showAudit(row));
    actions.append(detailsButton);
    if (currentState(inclusion) !== "excluded") {
      const excludeButton = el("button", {
        className: "lnt-btn lnt-btn-small btn-quiet",
        text: "Исключить…",
        attrs: { "aria-label": `Исключить участника ${row.sessionId}` },
      });
      excludeButton.addEventListener("click", () => this.excludeWithReason(row));
      actions.append(excludeButton);
    } else {
      const undoButton = el("button", {
        className: "lnt-btn lnt-btn-small btn-quiet",
        text: "Отменить исключение",
        attrs: { "aria-label": `Отменить исключение участника ${row.sessionId}` },
      });
      undoButton.addEventListener("click", () => this.undoExclusion(row));
      actions.append(undoButton);
    }
    tr.append(sessionCell, conditionCell, orderCell, verdictCell, stateCell, actions);
    return tr;
  }

  private excludeWithReason(row: MemberRow): void {
    const reason = row.verdict.reason_code ?? `manual_operator_decision:${row.health}`;
    this.options.store.excludeMember(this.options.experimentId, row.sessionId, reason);
    announcePolite(`Участник ${row.sessionId} исключён. Причина: ${reason}`);
    this.refresh();
  }

  private undoExclusion(row: MemberRow): void {
    try {
      this.options.store.undoMember(
        this.options.experimentId,
        row.sessionId,
        "оператор отменил исключение",
      );
      announcePolite(`Исключение участника ${row.sessionId} отменено, участник восстановлен`);
      this.refresh();
    } catch {
      // Отмена без предыдущего решения невозможна — состояние не меняется.
      announcePolite(`Отмена невозможна для ${row.sessionId}: нет предыдущего решения`);
    }
  }

  private refresh(): void {
    this.render();
    this.options.onInclusionChange?.();
  }

  private showAudit(row: MemberRow): void {
    const lines = auditLines(
      this.options.store.inclusion(this.options.experimentId, row.sessionId),
    );
    const host = el("div", { className: "lnt-exp-audit" });
    const list = el("ul", { attrs: { "aria-label": `История решений: ${row.sessionId}` } });
    for (const line of lines) list.append(el("li", { text: line }));
    host.append(list);
    this.body.append(host);
  }
}
