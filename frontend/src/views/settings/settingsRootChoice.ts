/** Блок выбора папки сессий: поле пути + копирование команды перезапуска.
 * Выделен рядом с settingsRootNote (та же V6-раскладка .ctl/.field/.btn),
 * но сервер НЕ трогает: корень меняется только перезапуском
 * `uv run lnt ui --root "<путь>"`. Проверка формы — validateSessionsFolder
 * (только форма записи; есть ли папка на диске, станет ясно при старте).
 * При недоступном/отклонённом clipboard текст поля выделяется, чтобы
 * пользователь скопировал команду вручную. */

import { el } from "../../components/primitives/dom";
import { createField } from "../../components/primitives/forms";
import { announcePolite } from "../../components/primitives/status";
import { validateSessionsFolder } from "./settingsModel";

export interface RootChoiceHandle {
  field: HTMLElement;
  copyButton: HTMLElement;
}

/** Чистый конструктор команды перезапуска: путь ВСЕГДА в двойных кавычках. */
export function folderRestartCommand(path: string): string {
  return `uv run lnt ui --root "${path.trim()}"`;
}

/** Поле пути и кнопка копирования команды перезапуска. */
export function createRootChoiceBlock(): RootChoiceHandle {
  const folderInput = el("input", {
    className: "ctl",
    attrs: {
      type: "text",
      id: "lnt-set-folder-path",
      autocomplete: "off",
      spellcheck: "false",
    },
  }) as HTMLInputElement;
  const folderField = createField({
    label: "Папка сессий (применится после перезапуска)",
    control: folderInput,
    hintText:
      "Папка проверяется при следующем запуске сервера: сначала останови сервер (Ctrl+C), затем запусти скопированной командой. Повторный запуск с другим --root живой сервер игнорирует.",
  });
  folderField.root.classList.add("field");
  folderField.root.querySelector("label")?.classList.add("field-label");
  const copyButton = el("button", {
    className: "btn",
    text: "Скопировать команду",
    attrs: { type: "button", id: "lnt-set-folder-copy" },
  });
  copyButton.addEventListener("click", () => void copyCommand());

  async function copyCommand(): Promise<void> {
    const validation = validateSessionsFolder(folderInput.value);
    folderField.setError(validation.error);
    if (!validation.ok) return;
    const command = folderRestartCommand(folderInput.value);
    try {
      if (
        typeof navigator === "undefined" ||
        navigator.clipboard === undefined ||
        typeof navigator.clipboard.writeText !== "function"
      ) {
        throw new Error("clipboard недоступен");
      }
      await navigator.clipboard.writeText(command);
      announcePolite("Команда перезапуска скопирована");
    } catch {
      // Fallback: выделить текст поля, чтобы пользователь скопировал вручную.
      folderInput.value = command;
      folderInput.focus();
      folderInput.select();
      announcePolite("Не удалось скопировать автоматически: команда подставлена в поле, скопируйте её вручную");
    }
  }

  return { field: folderField.root, copyButton };
}
