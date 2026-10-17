/** Сводка инспектора контекста по варианту «Плотный список»: плитки
 * идентификатор/дата/длительность/частота сети, строка здоровья контекста
 * с ревизией и секция тегов. Недоступное показывается словом «недоступно»
 * с причиной в title — ноль вместо пропущенного не подставляется. */

import type { SessionHealth } from "../../api/types";
import { el } from "../../components/primitives/dom";
import { HEALTH_LABELS } from "./catalogModel";
import type { SessionMetrics } from "./contextMetrics";

export interface SessionMeta {
  id: string;
  createdUtc: string | null;
  sessionHealth: string;
}

const DATE_FULL = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "UTC",
});
const NF1 = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const NF2 = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const CONTEXT_HEALTH: Readonly<Record<string, { label: string; tone: "ok" | "warn" | "error" }>> = {
  context_valid: { label: "Исправен", tone: "ok" },
  context_absent: { label: "Не сохранён", tone: "warn" },
  context_invalid: { label: "Повреждён", tone: "error" },
};

export function contextHealthInfo(health: string): {
  label: string;
  tone: "ok" | "warn" | "error";
} {
  return CONTEXT_HEALTH[health] ?? { label: health, tone: "warn" };
}

function readout(label: string, value: HTMLElement): HTMLElement {
  return el("div", { className: "ro" }, [el("dt", { text: label }), value]);
}

function unavailableValue(reason: string | null): HTMLElement {
  return el("dd", {
    className: "is-unavailable",
    text: "недоступно",
    attrs: reason === null ? {} : { title: reason },
  });
}

export function renderReadouts(meta: SessionMeta, metrics: SessionMetrics): HTMLElement {
  const parsed = meta.createdUtc === null ? null : new Date(meta.createdUtc);
  const dateText =
    parsed !== null && !Number.isNaN(parsed.getTime()) ? DATE_FULL.format(parsed) : "—";
  return el("dl", { className: "lnt-cat-session-summary readout-grid" }, [
    readout(
      "Идентификатор",
      el("dd", {
        className: "t-mono cell-ellipsis",
        text: meta.id,
        attrs: { title: "Идентификатор сессии" },
      }),
    ),
    readout("Дата", el("dd", { text: dateText })),
    readout(
      "Длительность",
      metrics.durationS === null
        ? unavailableValue(metrics.durationReason)
        : el("dd", { text: `${NF1.format(metrics.durationS)} с` }),
    ),
    readout(
      "Частота сети",
      metrics.mainsHz === null
        ? unavailableValue(metrics.mainsReason)
        : el("dd", { text: `${NF2.format(metrics.mainsHz)} Гц` }),
    ),
  ]);
}

export function renderHealthRow(health: string, revision: number, meta: SessionMeta): HTMLElement {
  const info = contextHealthInfo(health);
  const glyph = info.tone === "ok" ? "●" : info.tone === "warn" ? "▲" : "✕";
  const sessionLabel =
    HEALTH_LABELS[meta.sessionHealth as SessionHealth]?.label ?? (meta.sessionHealth || "—");
  return el("div", { className: "insp-health" }, [
    el(
      "span",
      {
        className: `lnt-status-pill lnt-tone-${info.tone}`,
        attrs: { "data-cat-context-health": health },
      },
      [
        el("span", { attrs: { "aria-hidden": "true" }, text: glyph }),
        document.createTextNode(`Контекст: ${info.label}`),
      ],
    ),
    el("span", {
      className: "t-compact insp-rev",
      text: `ревизия ${String(revision)} · сессия: ${sessionLabel}`,
      attrs: { "data-cat-revision": String(revision) },
    }),
  ]);
}

export function renderTagsSection(tags: string[]): HTMLElement {
  const body =
    tags.length === 0
      ? el("span", { className: "tag-empty", text: "Тегов нет" })
      : el(
          "div",
          { className: "tag-row" },
          tags.map((tag) =>
            el("span", { className: "tag-chip", text: tag, attrs: { title: tag } }),
          ),
        );
  return el("div", { className: "insp-section" }, [
    el("h3", { className: "insp-block-title", text: "Теги" }),
    body,
  ]);
}
