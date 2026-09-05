import type { CatalogSession } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { type CatalogRow, roleOf } from "./catalogColumnModel";
import type { PairStateValue } from "./pairState";

const DAY_FORMAT = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });

function assertNever(value: never): never {
  throw new Error(`unhandled catalog row ${String(value)}`);
}

function dayKey(createdUtc: string | null): string {
  if (!createdUtc) return "unknown";
  const matched = createdUtc.match(/^(\d{4}-\d{2}-\d{2})/);
  return matched?.[1] ?? "unknown";
}

function formatDay(day: string): string {
  const parsed = new Date(`${day}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? day : DAY_FORMAT.format(parsed);
}

function formatTime(createdUtc: string | null): string {
  if (!createdUtc) return "—";
  const match = /T(\d{2}):(\d{2})/.exec(createdUtc);
  if (!match) return "—";
  return `${match[1]}:${match[2]}`;
}

function roleLetter(role: "a" | "b"): string {
  switch (role) {
    case "a":
      return "А";
    case "b":
      return "Б";
    default:
      return assertNever(role);
  }
}

function roleChip(role: "a" | "b"): HTMLElement {
  return el("span", {
    className: `cat-role cat-role-${role}`,
    text: roleLetter(role),
    attrs: { "data-cat-role": role },
  });
}

function renderGroup(day: string, count: number): HTMLTableRowElement {
  return el("tr", { className: "cat-group", attrs: { "data-cat-group": day } }, [
    el("th", { attrs: { colspan: "4", scope: "colgroup" } }, [
      el("div", { className: "cat-group-in" }, [
        el("span", { text: formatDay(day) }),
        el("span", {
          className: "cat-group-count",
          text: String(count),
          attrs: { "data-cat-count": String(count) },
        }),
      ]),
    ]),
  ]);
}

function renderEmpty(): HTMLTableRowElement {
  return el("tr", {}, [
    el("td", {
      className: "cat-empty",
      text: "По запросу ничего не найдено",
      attrs: { colspan: "4", "data-cat-empty": "" },
    }),
  ]);
}

export interface CatalogRowRenderCtx {
  readonly grouped: boolean;
  readonly pair: PairStateValue;
  readonly onPick: (sessionId: string) => void;
}

function renderSession(session: CatalogSession, ctx: CatalogRowRenderCtx): HTMLTableRowElement {
  const day = dayKey(session.created_utc);
  const role = roleOf(session.id, ctx.pair);
  const roleCell = el("td");
  const labelCell = el("td", { className: "cat-label-cell" });
  if (role !== null) {
    labelCell.append(roleChip(role));
  }
  // V6: полное имя — в title, обрезанное эллипсисом читается по наведению.
  const fullLabel = session.label ?? session.id;
  labelCell.append(
    el("span", {
      className: "cell-ellipsis",
      text: fullLabel,
      attrs: { "data-cat-label": "", title: fullLabel },
    }),
  );
  const dateText = ctx.grouped ? formatTime(session.created_utc) : day === "unknown" ? "—" : day;
  const row = el("tr", { attrs: { "data-session": session.id, "data-cat-date": day } }, [
    roleCell,
    labelCell,
    el("td", { text: session.session_type ?? "—" }),
    el("td", { text: dateText }),
  ]);
  row.addEventListener("click", () => {
    ctx.onPick(session.id);
  });
  return row;
}

export function renderCatalogRow(row: CatalogRow, ctx: CatalogRowRenderCtx): HTMLTableRowElement {
  switch (row.kind) {
    case "group":
      return renderGroup(row.day, row.count);
    case "session":
      return renderSession(row.session, ctx);
    case "empty":
      return renderEmpty();
    default:
      return assertNever(row);
  }
}
