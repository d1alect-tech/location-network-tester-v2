/** Строка 13 (план ui-refactor-3, F3-remedy): чистые билдеры разметки строки
 * рейла каталога — вариант V1 «Мета под меткой» с инвариантом владельца:
 * полный текст метки всегда виден (никаких cell-ellipsis/nowrap/clamp),
 * элементы не наезжают. Выделено из catalogColumnRender.ts ради предела
 * 250 чистых LOC. Даты считаются строками из UTC-литералов — без
 * Date/Intl на created_utc (сдвиг зоны); formatDay парсит локальную
 * полночь keyset-дня, зоны не касается. */

import type { CatalogSession } from "../../api/types";
import { el } from "../../components/primitives/dom";
import {
  ANALYZED_LABEL,
  HEALTH_LABELS,
  UNANALYZED_LABEL,
  glyphForTone,
} from "../../components/status/sessionHealth";
import { sessionTypeLabel } from "../catalog/catalogModel";

const DAY_FORMAT = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

export function formatDay(day: string): string {
  if (day === "unknown") return "Без даты";
  const parsed = new Date(`${day}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? day : DAY_FORMAT.format(parsed);
}

export function formatTime(createdUtc: string | null): string {
  if (!createdUtc) return "—";
  const match = /T(\d{2}):(\d{2})/.exec(createdUtc);
  return match ? `${match[1]}:${match[2]}` : "—";
}

export function formatFlatDateTime(createdUtc: string | null): string {
  if (!createdUtc) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(createdUtc);
  return match ? `${match[3]}.${match[2]}.${match[1]}, ${match[4]}:${match[5]}` : "—";
}

export function roleChip(role: "a" | "b"): HTMLElement {
  const letter = role === "a" ? "А" : "Б";
  return el("span", {
    className: `cat-role cat-role-${role}`,
    text: letter,
    attrs: { "data-cat-role": role },
  });
}

function healthPill(session: CatalogSession): HTMLElement {
  const health = HEALTH_LABELS[session.health];
  const pill = el("span", {
    className: `lnt-status-pill lnt-tone-${health.tone} cat-health`,
    attrs: { "data-cat-health": session.health, title: `Состояние: ${health.label}` },
  });
  pill.append(
    el("span", { text: glyphForTone(health.tone), attrs: { "aria-hidden": "true" } }),
    document.createTextNode(health.label),
  );
  return pill;
}

function analyzedPill(analyzed: boolean, invalid: string | undefined): HTMLElement | null {
  if (invalid !== undefined) {
    return el("span", {
      className: "lnt-status-pill lnt-tone-error cat-analyzed",
      text: invalid,
      attrs: { "data-cat-analyzed": "invalid", title: invalid },
    });
  }
  if (analyzed) {
    return el("span", {
      className: "lnt-status-pill lnt-tone-ok cat-analyzed",
      text: ANALYZED_LABEL,
      attrs: { "data-cat-analyzed": "yes", title: ANALYZED_LABEL },
    });
  }
  return el("span", {
    className: "lnt-status-pill lnt-tone-warn cat-analyzed",
    text: UNANALYZED_LABEL,
    attrs: { "data-cat-analyzed": "no", title: UNANALYZED_LABEL },
  });
}

export function typeText(session: CatalogSession): string {
  return session.session_type ? sessionTypeLabel(session.session_type) : "—";
}

export function labelSpan(session: CatalogSession): HTMLElement {
  const fullLabel = session.label ?? session.id;
  return el("span", {
    className: "cat-label",
    text: fullLabel,
    attrs: { "data-cat-label": "", title: fullLabel },
  });
}

export function metaLine(
  session: CatalogSession,
  analyzed: boolean | undefined,
  invalid: string | undefined,
  grouped: boolean,
): HTMLElement {
  const meta = el("div", { className: "cat-meta" });
  meta.append(
    el("span", {
      className: "cat-meta-type",
      text: typeText(session),
      attrs: { "data-cat-type": session.session_type ?? "none" },
    }),
    healthPill(session),
  );
  if (analyzed !== undefined || invalid !== undefined) {
    const pill = analyzedPill(analyzed ?? false, invalid);
    if (pill !== null) meta.append(pill);
  }
  const timeText = grouped
    ? formatTime(session.created_utc)
    : formatFlatDateTime(session.created_utc);
  meta.append(
    el("span", {
      className: "cat-meta-time",
      text: timeText,
      attrs: { title: session.created_utc ?? timeText },
    }),
  );
  return meta;
}
