/** Разделитель панелей с клавиатурным изменением размера (стрелки),
 * aria-семантикой separator и сохранением пропорции в localStorage. */

import { el } from "./dom";

export interface SplitPaneHandle {
  root: HTMLElement;
  getRatio(): number;
  setRatio(ratio: number): void;
}

const MIN_RATIO = 20;
const MAX_RATIO = 80;
const STEP = 5;

export function createSplitPane(
  left: HTMLElement,
  right: HTMLElement,
  options: { initialRatio?: number; storageKey?: string } = {},
): SplitPaneHandle {
  const clamp = (value: number): number => Math.min(MAX_RATIO, Math.max(MIN_RATIO, value));

  let ratio = clamp(options.initialRatio ?? 50);
  if (options.storageKey) {
    const stored = window.localStorage.getItem(options.storageKey);
    const parsed = stored === null ? Number.NaN : Number(stored);
    if (Number.isFinite(parsed)) ratio = clamp(parsed);
  }

  const separator = el("div", {
    className: "lnt-split-separator",
    attrs: {
      role: "separator",
      "aria-orientation": "vertical",
      "aria-valuemin": String(MIN_RATIO),
      "aria-valuemax": String(MAX_RATIO),
    },
  });
  separator.tabIndex = 0;
  separator.setAttribute("aria-label", "Изменить ширину панелей");

  const leftPane = el("div", { className: "lnt-split-pane" }, [left]);
  const rightPane = el("div", { className: "lnt-split-pane" }, [right]);
  const root = el("div", { className: "lnt-split" }, [leftPane, separator, rightPane]);

  function apply(): void {
    root.style.setProperty("--lnt-split-ratio", `${ratio}%`);
    separator.setAttribute("aria-valuenow", String(Math.round(ratio)));
    if (options.storageKey) {
      window.localStorage.setItem(options.storageKey, String(Math.round(ratio)));
    }
  }

  separator.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") ratio = clamp(ratio + STEP);
    else if (event.key === "ArrowLeft") ratio = clamp(ratio - STEP);
    else return;
    event.preventDefault();
    apply();
  });

  apply();
  return {
    root,
    getRatio: () => Math.round(ratio),
    setRatio: (value) => {
      ratio = clamp(value);
      apply();
    },
  };
}
