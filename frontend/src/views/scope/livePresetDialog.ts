/** DOM-строители пресетов задач (сплит из livePresets, задача 17): секция
 * меню захвата, stateless-диалог и строка списка — только разметка,
 * поведение (слушатели, снимок, применение) — в livePresets. */

import { el } from "../../components/primitives/dom";
import type { LivePreset } from "./livePresetStore";

export interface LivePresetDom {
  readonly openButton: HTMLButtonElement;
  readonly section: HTMLElement;
  readonly dialog: HTMLElement;
  readonly nameInput: HTMLInputElement;
  readonly saveButton: HTMLButtonElement;
  readonly error: HTMLElement;
  readonly list: HTMLElement;
}

export function buildLivePresetDom(): LivePresetDom {
  const openButton = el("button", {
    className: "lnt-live-presets-btn",
    text: "Открыть…",
    attrs: { type: "button", "data-presets-open": "", "aria-haspopup": "dialog" },
  });
  const section = el(
    "div",
    { className: "lnt-live-capture-group", attrs: { "data-menu-section": "presets" } },
    [
      el(
        "div",
        {
          className: "lnt-live-capture-row",
          attrs: { role: "group", "aria-label": "Пресеты задач" },
        },
        [el("span", { className: "lnt-live-capture-row-label", text: "Пресеты" }), openButton],
      ),
    ],
  );

  const nameInput = el("input", {
    className: "lnt-live-capture-level-input",
    attrs: {
      type: "text",
      "data-presets-name": "",
      "aria-label": "Имя пресета",
      placeholder: "имя",
      autocomplete: "off",
    },
  });
  const saveButton = el("button", {
    className: "lnt-live-presets-btn",
    text: "Сохранить текущие",
    attrs: { type: "button", "data-presets-save": "" },
  });
  const error = el("p", {
    className: "t-compact lnt-live-capture-hint",
    text: "имя пустое",
    attrs: { "data-presets-error": "", role: "alert", hidden: "" },
  });
  const list = el("div", {
    className: "lnt-live-presets-list",
    attrs: { "data-presets-list": "" },
  });
  const dialog = el(
    "div",
    {
      className: "lnt-live-presets",
      attrs: { role: "dialog", "aria-label": "Пресеты задач", hidden: "" },
    },
    [
      el("span", { className: "lnt-live-menu-hd", text: "Пресеты задач" }),
      el(
        "div",
        {
          className: "lnt-live-capture-row",
          attrs: { role: "group", "aria-label": "Имя пресета" },
        },
        [nameInput, saveButton],
      ),
      error,
      list,
      el("p", {
        className: "t-compact lnt-live-capture-hint",
        text: "В/дел, пробник и частота — при следующем запуске; триггер на ходу — сразу; ФНЧ, послесвечение и ряды измерений — отображение.",
      }),
    ],
  );

  return { openButton, section, dialog, nameInput, saveButton, error, list };
}

/** Строка списка: имя + «Применить» + «Удалить» (data-preset-name). */
export function buildLivePresetRow(preset: LivePreset): HTMLElement {
  return el(
    "div",
    { className: "lnt-live-presets-item", attrs: { "data-preset-name": preset.name } },
    [
      el("span", { className: "lnt-live-presets-name", text: preset.name }),
      el("button", {
        className: "lnt-live-presets-btn",
        text: "Применить",
        attrs: { type: "button", "data-presets-apply": "" },
      }),
      el("button", {
        className: "lnt-live-presets-btn",
        text: "Удалить",
        attrs: {
          type: "button",
          "data-presets-remove": "",
          "aria-label": `Удалить ${preset.name}`,
        },
      }),
    ],
  );
}
