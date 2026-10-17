/** Полоса пары A/B инспекции v6: База / Сравнение, глиф health, обмен слотов. */

import type { CatalogSession } from "../../api/types";
import "./pairbarArm.css";
import { clearElement, el } from "../../components/primitives/dom";
import { HEALTH_LABELS, glyphForTone } from "../../components/status/sessionHealth";
import { type DeltaSummary, formatDeltaDb } from "./deltaSummary";
import type { PairSlot } from "./pairState";

export interface PairbarV6Options {
  readonly onSwap: () => void;
  /** M1 (todo 5): слот-клик — не режим и не мутация пары: провод фокуса
   * рейла каталога (пульс кнопок назначаемого слота). */
  readonly onSlotTap?: (slot: PairSlot) => void;
}

export interface PairbarV6Handle {
  readonly root: HTMLElement;
  setPair(base: CatalogSession | null, compare: CatalogSession | null): void;
  setDelta(summary: DeltaSummary | null): void;
  /** Вооружённый слот подсвечен; null — ни один. */
  setArmed(slot: PairSlot | null): void;
  /** Блокировка контролов на время in-flight задачи анализа (job-busy). */
  setBusy(busy: boolean): void;
}

function sessionName(session: CatalogSession | null): string {
  if (session === null) return "—";
  return session.label ?? session.id;
}

function sessionMeta(session: CatalogSession | null): string {
  if (session === null) return "—";
  const type = session.session_type ?? "—";
  // F-5: бэкенд отдаёт exclude_none — created_utc может отсутствовать вовсе
  // (undefined), а guard каталога это пропускает; нестроковое значение тоже не
  // режем. Только строка даёт дату, всё остальное — честный прочерк.
  const created = session.created_utc;
  const date = typeof created === "string" ? created.slice(0, 10) : "—";
  return `${type} · ${date}`;
}

function healthGlyph(session: CatalogSession | null): HTMLElement {
  const health = session === null ? null : HEALTH_LABELS[session.health];
  const mark = health === null ? "·" : glyphForTone(health.tone);
  const label = session === null ? "unknown" : (health?.label ?? session.health);
  return el("span", {
    className: `glyph glyph-${session === null ? "unknown" : session.health}`,
    text: mark,
    attrs: { title: label, "aria-label": label },
  });
}

function fillSlot(slotEl: HTMLElement, role: string, session: CatalogSession | null): void {
  clearElement(slotEl);
  slotEl.append(
    el("span", { className: "pair-role", text: role }),
    healthGlyph(session),
    el("span", { className: "pair-name", text: sessionName(session) }),
    el("span", { className: "pair-meta", text: sessionMeta(session) }),
  );
}

export function createPairbar(opts: PairbarV6Options): PairbarV6Handle {
  const slotA = el("button", {
    className: "pair-slot",
    attrs: {
      type: "button",
      "data-pair": "a",
      "aria-pressed": "false",
      title: "База. Назначить: кнопка А у строки в каталоге",
    },
  });
  const slotB = el("button", {
    className: "pair-slot",
    attrs: {
      type: "button",
      "data-pair": "b",
      "aria-pressed": "false",
      title: "Сравнение. Назначить: клик по строке или кнопка Б",
    },
  });
  const meanBadge = el("span", {
    className: "pair-badge",
    attrs: { "data-pair-delta": "mean" },
    text: "Δср —",
  });
  const maxBadge = el("span", {
    className: "pair-badge",
    attrs: { "data-pair-delta": "max" },
    text: "Δmax —",
  });
  const pathEl = el("span", { className: "pair-path" });
  const swap = el("button", {
    className: "btn-quiet",
    text: "Поменять местами",
    attrs: { type: "button", "data-pair-swap": "" },
  });
  swap.addEventListener("click", () => opts.onSwap());
  // M1 (todo 5): слот-клик — только onSlotTap (фокус рейла), не арм
  // и не мутация пары.
  slotA.addEventListener("click", () => opts.onSlotTap?.("a"));
  slotB.addEventListener("click", () => opts.onSlotTap?.("b"));
  let busy = false;
  let compareNull = true;
  const root = el("div", { className: "pairbar" }, [
    slotA,
    el("span", { className: "pair-delta", text: "Δ", attrs: { "aria-hidden": "true" } }),
    slotB,
    meanBadge,
    maxBadge,
    pathEl,
    swap,
  ]);

  function setPair(base: CatalogSession | null, compare: CatalogSession | null): void {
    fillSlot(slotA, "База", base);
    fillSlot(slotB, "Сравнение", compare);
    const path = compare === null ? "—" : (compare.storage_path ?? compare.id);
    pathEl.textContent = path;
    pathEl.title = path;
    compareNull = compare === null;
    swap.toggleAttribute("disabled", busy || compareNull);
  }

  function setArmed(slot: PairSlot | null): void {
    for (const [node, key] of [
      [slotA, "a"],
      [slotB, "b"],
    ] as const) {
      const armed = slot === key;
      node.classList.toggle("pair-armed", armed);
      node.setAttribute("aria-pressed", armed ? "true" : "false");
    }
  }

  function setBusy(next: boolean): void {
    busy = next;
    slotA.toggleAttribute("disabled", busy);
    slotB.toggleAttribute("disabled", busy);
    swap.toggleAttribute("disabled", busy || compareNull);
  }

  function setDelta(summary: DeltaSummary | null): void {
    meanBadge.textContent = summary === null ? "Δср —" : `Δср ${formatDeltaDb(summary.meanDb)}`;
    maxBadge.textContent = summary === null ? "Δmax —" : `Δmax ${formatDeltaDb(summary.maxAbsDb)}`;
  }

  setPair(null, null);
  return { root, setPair, setDelta, setArmed, setBusy };
}
