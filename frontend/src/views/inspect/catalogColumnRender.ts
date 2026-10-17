/** Ряды рейла каталога инспекции. Строка 13 (план ui-refactor-3, F3-remedy):
 * строка сессии — ОДНА colspan-ячейка с контуром .cat-row (линия метки +
 * мета-строка под ней, вариант V1 «Мета под меткой»); инвариант владельца —
 * ничего не обрезается и не наезжает (полный перенос метки, мета
 * flex-wrap). Билдеры разметки — в catalogRowMarkup.ts. Атрибуты строк
 * (data-session/data-rowkey/data-in-pair) — замороженный CONTRACT. */

import type { CatalogSession } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { loadKey } from "./bootPick";
import { assignButtons } from "./catalogAssign";
import { type CatalogRow, roleOf } from "./catalogColumnModel";
import { formatDay, labelSpan, metaLine, roleChip } from "./catalogRowMarkup";
import "./catalogRowMarkup.css";
import type { PairSlot, PairStateValue } from "./pairState";

function assertNever(value: never): never {
  throw new Error(`unhandled catalog row ${String(value)}`);
}

function dayKey(createdUtc: string | null): string {
  if (!createdUtc) return "unknown";
  const matched = createdUtc.match(/^(\d{4}-\d{2}-\d{2})/);
  return matched?.[1] ?? "unknown";
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
  readonly analyzedOf: (session: CatalogSession) => boolean | undefined;
  readonly invalidOf: (session: CatalogSession) => string | undefined;
  readonly onPick: (loadKey: string) => void;
  readonly onAssign: (slot: PairSlot, loadKey: string) => void;
  readonly onFocus: (sessionId: string) => void;
}

function focusRow(row: HTMLElement, ctx: CatalogRowRenderCtx): void {
  const rows = row.closest("tbody")?.querySelectorAll<HTMLElement>("tr[data-session]") ?? [];
  for (const item of rows) item.tabIndex = item === row ? 0 : -1;
  ctx.onFocus(row.getAttribute("data-session") ?? "");
}

function moveFocus(event: KeyboardEvent, row: HTMLElement): boolean {
  const rows = [...(row.closest("tbody")?.querySelectorAll<HTMLElement>("tr[data-session]") ?? [])];
  const index = rows.indexOf(row);
  const target =
    event.key === "ArrowDown"
      ? rows[Math.min(rows.length - 1, index + 1)]
      : event.key === "ArrowUp"
        ? rows[Math.max(0, index - 1)]
        : event.key === "Home"
          ? rows[0]
          : event.key === "End"
            ? rows.at(-1)
            : undefined;
  if (target === undefined) return false;
  event.preventDefault();
  target.focus();
  return true;
}

function renderSession(session: CatalogSession, ctx: CatalogRowRenderCtx): HTMLTableRowElement {
  const day = dayKey(session.created_utc);
  const role = roleOf(session, loadKey, ctx.pair);
  const key = loadKey(session);
  const assign = assignButtons(
    { id: session.id, name: session.label, loadKey: key, health: session.health },
    role,
  );
  assign.onAssign = ctx.onAssign;
  const line1 = el("div", { className: "cat-line1" }, [assign.el]);
  if (role !== null) {
    line1.append(roleChip(role));
  }
  line1.append(labelSpan(session));
  const cell = el("td", { attrs: { colspan: "4" } }, [
    el("div", { className: "cat-row" }, [
      line1,
      metaLine(session, ctx.analyzedOf(session), ctx.invalidOf(session), ctx.grouped),
    ]),
  ]);
  const row = el(
    "tr",
    {
      attrs: {
        "data-session": session.id,
        "data-rowkey": key !== session.id ? key : session.id,
        "data-cat-date": day,
        tabindex: "-1",
        ...(role !== null ? { "data-in-pair": role } : {}),
      },
    },
    [cell],
  );
  row.addEventListener("focus", () => focusRow(row, ctx));
  row.addEventListener("click", () => {
    row.focus();
    ctx.onPick(key);
  });
  row.addEventListener("keydown", (event) => {
    assign.handleKeydown(event);
    if (moveFocus(event, row)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    ctx.onPick(key);
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
