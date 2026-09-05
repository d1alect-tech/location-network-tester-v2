/** Локальная заметка о корне сессий: поле + кнопка сохранения.
 * Выделено из settingsWorkspace (бюджет 250 чистых LOC) без смены разметки:
 * фактический корень отдаёт сервер, заметка живёт только в localStorage.
 * V6 (D3=A): .ctl на поле, .field/.field-label поверх примитива, .btn на
 * кнопке — токены committed-волны сохранены байт в байт. */

import { el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";
import { announcePolite } from "../../components/primitives/status";
import { ROOT_NOTE_MAX_LENGTH, validateRootNote } from "./settingsModel";

const ROOT_NOTE_KEY = "lnt-root-note";

export interface RootNoteHandle {
  field: HTMLElement;
  saveButton: HTMLElement;
}

/** Поле заметки и кнопка сохранения для секции корня сессий. */
export function createRootNoteBlock(): RootNoteHandle {
  const rootNoteInput = el("input", {
    className: "ctl",
    attrs: {
      type: "text",
      id: "lnt-set-root-note",
      maxlength: String(ROOT_NOTE_MAX_LENGTH),
      autocomplete: "off",
    },
  });
  const rootNoteField = createField({
    label: "Локальная заметка о корне (не меняет сервер)",
    control: rootNoteInput,
    hintText:
      "Фактический корень отдаёт сервер и меняется только перезапуском: uv run lnt ui --root <путь>. Заметка хранится локально в браузере.",
  });
  // V6-форма поверх примитива (примитив не трогаем — он общий для разделов):
  // .field для раскладки, .field-label для подписи; .lnt-field остаётся e2e-хуком.
  rootNoteField.root.classList.add("field");
  rootNoteField.root.querySelector("label")?.classList.add("field-label");
  const savedNote = readNote();
  if (savedNote !== null) rootNoteInput.value = savedNote;
  const saveButton = el("button", {
    className: "btn",
    text: "Сохранить заметку",
    attrs: { type: "button", id: "lnt-set-root-save" },
  });
  saveButton.addEventListener("click", () => saveNote());

  function readNote(): string | null {
    try {
      return window.localStorage.getItem(ROOT_NOTE_KEY);
    } catch {
      return null;
    }
  }

  function saveNote(): void {
    const validation = validateRootNote(rootNoteInput.value);
    rootNoteField.setError(validation.error);
    if (!validation.ok) return;
    try {
      if (rootNoteInput.value.trim() === "") window.localStorage.removeItem(ROOT_NOTE_KEY);
      else window.localStorage.setItem(ROOT_NOTE_KEY, rootNoteInput.value.trim());
    } catch {
      // приватный режим: заметка живёт только в поле ввода
    }
    announcePolite("Заметка о корне сохранена локально");
  }

  return { field: rootNoteField.root, saveButton };
}
