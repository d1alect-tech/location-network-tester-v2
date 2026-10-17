/** Каркас сигнального окна: тумблер вида, строка статуса с повтором и кадр
 * чарта. Вынесено из spectrumPanelV6.ts (потолок 250 чистых LOC); поведение
 * тумблера, статуса и повтора остаётся в панели. */

import { el } from "../../components/primitives/dom";

export type SpectrumPanelChrome = {
  readonly viewToggle: HTMLElement;
  readonly spectrumBtn: HTMLButtonElement;
  readonly gramBtn: HTMLButtonElement;
  readonly status: HTMLElement;
  readonly statusText: HTMLElement;
  readonly retryButton: HTMLButtonElement;
  readonly frame: HTMLElement;
};

export function createSpectrumPanelChrome(): SpectrumPanelChrome {
  const spectrumBtn = el("button", {
    className: "btn-quiet view-toggle-btn",
    text: "Спектр",
    attrs: { type: "button", "data-spectrum-view": "spectrum", "aria-pressed": "true" },
  }) as HTMLButtonElement;
  const gramBtn = el("button", {
    className: "btn-quiet view-toggle-btn",
    text: "Спектрограмма",
    attrs: { type: "button", "data-spectrum-view": "gram", "aria-pressed": "false" },
  }) as HTMLButtonElement;
  const viewToggle = el(
    "div",
    { className: "view-toggle", attrs: { role: "group", "aria-label": "Вид сигнального окна" } },
    [spectrumBtn, gramBtn],
  );
  const frame = el("div", { className: "frame" });
  const statusText = el("span", {});
  const retryButton = el("button", {
    className: "lnt-btn btn-quiet",
    text: "Пересчитать спектр",
    attrs: { type: "button" },
  }) as HTMLButtonElement;
  const status = el(
    "div",
    { className: "spectrum-status", attrs: { role: "status", "data-spectrum-status": "" } },
    [statusText, retryButton],
  );
  status.hidden = true;
  return { viewToggle, spectrumBtn, gramBtn, status, statusText, retryButton, frame };
}
