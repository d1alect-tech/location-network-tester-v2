/** Полоса пары A/B инспекции v6: База / Сравнение, глиф health, обмен слотов. */

import type { CatalogSession, SessionHealth } from "../../api/types";
import { clearElement, el } from "../../components/primitives/dom";
import { type DeltaSummary, formatDeltaDb } from "./deltaSummary";

export interface PairbarV6Options {
  readonly onSwap: () => void;
}

export interface PairbarV6Handle {
  readonly root: HTMLElement;
  setPair(base: CatalogSession | null, compare: CatalogSession | null): void;
  setDelta(summary: DeltaSummary | null): void;
}

const HEALTH_GLYPH = {
  ok: "●",
  partial: "▲",
  duplicate_id: "▲",
  corrupt_manifest: "✕",
  missing_files: "✕",
  context_invalid: "✕",
  analysis_invalid: "✕",
} as const satisfies Record<SessionHealth, string>;

function sessionName(session: CatalogSession | null): string {
  if (session === null) return "—";
  return session.label ?? session.id;
}

function sessionMeta(session: CatalogSession | null): string {
  if (session === null) return "—";
  const type = session.session_type ?? "—";
  const date = session.created_utc === null ? "—" : session.created_utc.slice(0, 10);
  return `${type} · ${date}`;
}

function healthGlyph(session: CatalogSession | null): HTMLElement {
  const health = session === null ? "unknown" : session.health;
  const mark = session === null ? "·" : HEALTH_GLYPH[session.health];
  return el("span", {
    className: `glyph glyph-${health}`,
    text: mark,
    attrs: { title: health, "aria-label": health },
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
  const slotA = el("div", { className: "pair-slot", attrs: { "data-pair": "a" } });
  const slotB = el("div", { className: "pair-slot", attrs: { "data-pair": "b" } });
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
  }

  function setDelta(summary: DeltaSummary | null): void {
    meanBadge.textContent = summary === null ? "Δср —" : `Δср ${formatDeltaDb(summary.meanDb)}`;
    maxBadge.textContent = summary === null ? "Δmax —" : `Δmax ${formatDeltaDb(summary.maxAbsDb)}`;
  }

  setPair(null, null);
  return { root, setPair, setDelta };
}
