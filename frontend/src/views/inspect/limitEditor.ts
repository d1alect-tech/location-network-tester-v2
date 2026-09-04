/** B4 limit-line editor: user masks in localStorage, never in manifest.json. */

import { el } from "../../components/primitives/dom";
import { type LimitMask, evaluateMask, parseLimitMask } from "./limitLines";

export const LIMIT_STORAGE_KEY = "lnt.limit-masks.v1";

export function readStoredMasks(storage: Storage): readonly LimitMask[] {
  try {
    const raw = storage.getItem(LIMIT_STORAGE_KEY);
    if (raw === null || raw.length === 0) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const masks: LimitMask[] = [];
    for (const item of parsed) {
      const mask = parseLimitMask(item);
      if (mask !== null && mask.points.length > 0) masks.push(mask);
    }
    return masks;
  } catch {
    return [];
  }
}

export function writeStoredMasks(storage: Storage, masks: readonly LimitMask[]): void {
  storage.setItem(LIMIT_STORAGE_KEY, JSON.stringify(masks));
}

export function previewVerdict(masks: readonly LimitMask[], x: number, value: number): string {
  const first = masks[0];
  if (first === undefined || !Number.isFinite(x) || !Number.isFinite(value)) return "N/A";
  const verdict = evaluateMask(x, value, first);
  if (verdict === "pass") return `PASS vs ${first.name}`;
  if (verdict === "fail") return `FAIL vs ${first.name}`;
  return "N/A";
}

export function mountLimitEditor(host: HTMLElement, storage: Storage): void {
  const title = el("h3", { text: "Limit lines" });
  const hint = el("p", {
    text: "Masks live in browser storage, never in manifest.json.",
  });
  const list = el("ul", { className: "lnt-limit-list" });
  const refresh = (): void => {
    list.replaceChildren();
    for (const mask of readStoredMasks(storage)) {
      list.append(el("li", { text: `${mask.name} [${mask.unit}] (${mask.points.length} pts)` }));
    }
    if (list.childElementCount === 0) {
      list.append(el("li", { text: "No masks — verdicts show N/A, never fabricated." }));
    }
  };
  refresh();
  host.append(title, hint, list);
}
