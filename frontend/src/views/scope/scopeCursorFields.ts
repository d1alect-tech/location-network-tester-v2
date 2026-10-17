/** Поле курсора (подпись + ползунок) — строитель пар для секции «Курсоры».
 * Сплит задачи r5-9: секция упёрлась в потолок 250 чистых LOC — чистый
 * DOM-строитель уходит в свой модуль, поведение без изменений. */

import { el } from "../../components/primitives/dom";

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
