/** Поле курсора (подпись + ползунок) — строитель пар для секции «Курсоры».
 * Сплит задачи r5-9: секция упёрлась в потолок 250 чистых LOC — чистый
 * DOM-строитель уходит в свой модуль, поведение без изменений. */

import { el } from "../../components/primitives/dom";
import type { CursorPositions } from "./scopeCursorModel";

export interface CursorField {
  readonly field: HTMLElement;
  readonly input: HTMLInputElement;
}

export function cursorField(
  id: string,
  label: string,
  min: number,
  max: number,
  value: number,
  sliderClass: string,
): CursorField {
  const input = el("input", {
    className: `lnt-scope-cursor-slider ${sliderClass}`,
    attrs: {
      type: "range",
      id,
      min: String(min),
      max: String(max),
      step: "5",
      value: String(value),
      "aria-label": label,
    },
  });
  const caption = el("label", { className: "lnt-scope-cursor-label", text: label });
  caption.htmlFor = id;
  return {
    input,
    field: el("div", { className: "lnt-scope-cursor-field" }, [caption, input]),
  };
}

/** Шкала ползунков V1/V2 следует окну развёртки и удерживает курсоры внутри. */
export function setVoltageCursorWindow(
  v1: HTMLInputElement,
  v2: HTMLInputElement,
  positions: CursorPositions,
  half: number,
): void {
  for (const [input, key] of [
    [v1, "v1"],
    [v2, "v2"],
  ] as const) {
    input.min = String(-half * 100);
    input.max = String(half * 100);
    input.step = String(half / 5);
    positions[key] = Math.max(-half, Math.min(half, positions[key]));
    input.value = String(positions[key] * 100);
  }
}
