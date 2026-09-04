/** Строки плотной V6-таблицы каталога (T11: выделено из catalogListView —
 * было 378 чистых LOC). Чистые рендеры строк/групп/пусто, сортировка и роли
 * А/Б; состояние (items/selectedId/activeIndex) остаётся в createCatalogListView
 * и передаётся сюда контекстом. Без смены разметки и классов e2e-пинов. */

import type { CatalogSession } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { HEALTH_LABELS, sessionTypeLabel } from "./catalogModel";

export type SortKey = "label" | "type" | "date";
export type SortDir = "ascending" | "descending";

const DAY_FORMAT = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });

const ROLE_TITLE: Readonly<Record<"a" | "b", string>> = {
  a: "Слот А полосы сравнения: база",
  b: "Слот Б полосы сравнения: сравнение",
};

const GLYPH_BY_TONE: Readonly<Record<string, string>> = {
  ok: "●",
  warn: "▲",
  error: "✕",
};

export function dayKey(createdUtc: string | null): string {
  if (!createdUtc) return "unknown";
  const matched = /^(\d{4}-\d{2}-\d{2})/.exec(createdUtc);
  return matched?.[1] ?? "unknown";
}

export function formatDay(day: string): string {
  if (day === "unknown") return "Без даты";
  const parsed = new Date(`${day}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? day : DAY_FORMAT.format(parsed);
}

/** В группе день уже назван заголовком — внутри дня различаем время. */
export function formatTime(createdUtc: string | null): string {
  if (!createdUtc) return "—";
  const matched = /T(\d{2}):(\d{2})/.exec(createdUtc);
  return matched ? `${matched[1]}:${matched[2]}` : "—";
}

export function sortValue(session: CatalogSession, key: SortKey): string {
  if (key === "label") return session.label ?? session.id;
  if (key === "type") return session.session_type ? sessionTypeLabel(session.session_type) : "";
  return session.created_utc ?? "";
}

export function orderSessions(
  items: CatalogSession[],
  sort: SortKey,
  dir: SortDir,
): CatalogSession[] {
  return [...items].sort((left, right) => {
    const order = sortValue(left, sort).localeCompare(sortValue(right, sort), "ru");
    const signed = dir === "ascending" ? order : -order;
    return signed === 0 ? left.id.localeCompare(right.id) : signed;
  });
}

/** Роль строки: активная сессия — А (слот базы), первый отличный кандидат — Б. */
export function roleOfSession(
  items: CatalogSession[],
  selectedId: string | null,
  sessionId: string,
): "a" | "b" | null {
  const anchor = selectedId ?? items[0]?.id ?? null;
  if (sessionId === anchor) return "a";
  const second = items.find((item) => item.id !== anchor)?.id ?? null;
  if (sessionId === second) return "b";
  return null;
}

function roleChip(role: "a" | "b"): HTMLElement {
  return el("span", {
    className: `cat-role cat-role-${role}`,
    text: role === "a" ? "А" : "Б",
    attrs: { "data-cat-role": role, title: ROLE_TITLE[role] },
  });
}

export interface RowRenderContext {
  activeIndex: number;
  selectedId: string | null;
  /** true — строки внутри групп дней (дата колонкой времени). */
  grouped: boolean;
  roleOf(sessionId: string): "a" | "b" | null;
  onActivate(index: number): void;
  onRowKeys(event: KeyboardEvent, index: number): void;
}

export function renderRow(
  session: CatalogSession,
  index: number,
  ctx: RowRenderContext,
): HTMLElement {
  const health = HEALTH_LABELS[session.health];
  const row = el("tr", {
    className: `lnt-cat-row${session.id === ctx.selectedId ? " lnt-cat-row-selected is-selected" : ""}`,
    attrs: {
      tabindex: index === ctx.activeIndex ? "0" : "-1",
      "data-pos": String(index),
      "data-session-id": session.id,
      "data-session": session.id,
      "data-cat-date": dayKey(session.created_utc),
      title: session.storage_path ?? session.id,
    },
  });

  const pill = el("span", { className: `lnt-status-pill lnt-tone-${health.tone}` });
  const glyph = el("span", { attrs: { "aria-hidden": "true" } });
  glyph.textContent = GLYPH_BY_TONE[health.tone] ?? "●";
  pill.append(glyph, document.createTextNode(health.label));
  const stateCell = el(
    "td",
    {
      className: "lnt-cat-cell",
      attrs: { title: `Состояние: ${health.label}` },
    },
    [pill],
  );

  const labelCell = el("td", { className: "cat-label-cell lnt-cat-cell" });
  const labelText = session.label ?? session.id;
  labelCell.append(
    el("span", {
      className: "cell-ellipsis",
      text: labelText,
      attrs: { "data-cat-label": "", title: session.label ? `Метка: ${session.label}` : labelText },
    }),
  );
  const role = ctx.roleOf(session.id);
  if (role !== null) labelCell.append(roleChip(role));

  const typeLabel = session.session_type ? sessionTypeLabel(session.session_type) : "—";
  const typeCell = el("td", {
    className: "cell-ellipsis",
    text: typeLabel,
    attrs: { title: typeLabel },
  });

  const dateText = ctx.grouped ? formatTime(session.created_utc) : dayKey(session.created_utc);
  const dateCell = el("td", {
    className: "num",
    text: dateText,
    attrs: { title: session.created_utc ?? dateText },
  });

  row.append(stateCell, labelCell, typeCell, dateCell);
  row.addEventListener("click", () => ctx.onActivate(index));
  row.addEventListener("keydown", (event) => ctx.onRowKeys(event, index));
  return row;
}

export function renderGroup(day: string, count: number): HTMLElement {
  return el("tr", { className: "cat-group", attrs: { "data-cat-group": day } }, [
    el("th", { attrs: { colspan: "4", scope: "colgroup" } }, [
      el("div", { className: "cat-group-in" }, [
        el("span", { text: formatDay(day) }),
        el("span", {
          className: "cat-group-count",
          text: String(count),
          attrs: { "data-cat-count": "" },
        }),
      ]),
    ]),
  ]);
}

export function renderEmpty(message: string): HTMLElement {
  return el("tr", {}, [
    el("td", {
      className: "cat-empty lnt-cat-empty",
      text: message,
      attrs: { colspan: "4", "data-cat-empty": "" },
    }),
  ]);
}

/** Тон баннера каталога на тонах T10: error — role=alert, warn/info — role=status. */
export type CatalogBannerTone = "error" | "warn" | "info";

const BANNER_TONE: Record<CatalogBannerTone, { modifier: string; glyph: string }> = {
  error: { modifier: "", glyph: "✕" },
  warn: { modifier: " banner-warn", glyph: "▲" },
  info: { modifier: " banner-info", glyph: "●" },
};

export function renderErrorBanner(
  message: string,
  onRetry: () => void,
  tone: CatalogBannerTone = "error",
): HTMLElement {
  const config = BANNER_TONE[tone];
  const banner = el("div", {
    className: `banner banner-inline lnt-cat-error${config.modifier}`,
    attrs: tone === "error" ? { role: "alert" } : { role: "status" },
  });
  banner.append(
    el("span", {
      className: "banner-glyph",
      text: config.glyph,
      attrs: { "aria-hidden": "true" },
    }),
    el("p", { className: "banner-msg", text: message }),
    el("button", { className: "btn btn-secondary", text: "Повторить", attrs: { type: "button" } }),
  );
  banner.querySelector("button")?.addEventListener("click", onRetry);
  return banner;
}

/** Точечная перекраска выбора и ролей без пересборки строк (не роняем фокус). */
export function paintSelection(
  tbody: HTMLElement,
  selectedId: string | null,
  roleOf: (sessionId: string) => "a" | "b" | null,
): void {
  for (const node of tbody.querySelectorAll<HTMLElement>(".lnt-cat-row")) {
    const id = node.getAttribute("data-session-id");
    const isSelected = id === selectedId;
    node.classList.toggle("lnt-cat-row-selected", isSelected);
    node.classList.toggle("is-selected", isSelected);
    node.querySelector(".cat-role")?.remove();
    if (id !== null) {
      const role = roleOf(id);
      if (role !== null) node.querySelector(".cat-label-cell")?.append(roleChip(role));
    }
  }
}
