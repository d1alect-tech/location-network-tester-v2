/** Предпочтение темы (система/светлая/тёмная): localStorage + data-theme.
 * Системный режим следит за prefers-color-scheme; выбор переживает
 * перезагрузку. Ничего не знает о бэкенде — это локальная настройка панели. */

export type ThemeChoice = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "lnt-theme";

const CHOICES: readonly ThemeChoice[] = ["system", "light", "dark"];

const LABELS: Record<ThemeChoice, string> = {
  system: "Системная",
  light: "Светлая",
  dark: "Тёмная",
};

export interface ThemeController {
  get(): ThemeChoice;
  set(choice: ThemeChoice): void;
  /** Применяет текущий выбор к documentElement (data-theme). */
  apply(): void;
  /** Переключатель для шапки: нативные radio в fieldset с легендой. */
  control(): HTMLElement;
  dispose(): void;
}

function isThemeChoice(value: unknown): value is ThemeChoice {
  return typeof value === "string" && (CHOICES as readonly string[]).includes(value);
}

export function createThemePreference(win: Window = window): ThemeController {
  let choice: ThemeChoice = readStored(win);
  const media =
    typeof win.matchMedia === "function" ? win.matchMedia("(prefers-color-scheme: dark)") : null;
  const onMediaChange = (): void => {
    if (choice === "system") apply();
  };
  media?.addEventListener?.("change", onMediaChange);

  function systemPrefersDark(): boolean {
    return media?.matches === true;
  }

  function resolved(): Exclude<ThemeChoice, "system"> {
    if (choice !== "system") return choice;
    return systemPrefersDark() ? "dark" : "light";
  }

  function apply(): void {
    win.document.documentElement.setAttribute("data-theme", resolved());
  }

  function readStored(target: Window): ThemeChoice {
    try {
      const raw = target.localStorage.getItem(THEME_STORAGE_KEY);
      return isThemeChoice(raw) ? raw : "system";
    } catch {
      return "system";
    }
  }

  apply();

  return {
    get: () => choice,
    set(next: ThemeChoice) {
      if (!isThemeChoice(next)) return;
      choice = next;
      try {
        win.localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        // localStorage может быть недоступен (приватный режим) — выбор живёт в памяти.
      }
      apply();
    },
    apply,
    control() {
      const fieldset = win.document.createElement("fieldset");
      fieldset.className = "lnt-theme-switch";
      const legend = win.document.createElement("legend");
      legend.className = "lnt-visually-hidden";
      legend.textContent = "Тема оформления";
      fieldset.append(legend);
      for (const item of CHOICES) {
        const radio = win.document.createElement("input");
        radio.type = "radio";
        radio.name = "lnt-theme-choice";
        radio.value = item;
        radio.id = `lnt-theme-${item}`;
        radio.checked = choice === item;
        radio.addEventListener("change", () => {
          if (radio.checked) this.set(item);
        });
        const label = win.document.createElement("label");
        label.htmlFor = radio.id;
        label.className = "lnt-theme-option";
        label.textContent = LABELS[item];
        label.title = `Тема: ${LABELS[item]}`;
        label.append(radio);
        fieldset.append(label);
      }
      return fieldset;
    },
    dispose() {
      media?.removeEventListener?.("change", onMediaChange);
    },
  };
}
