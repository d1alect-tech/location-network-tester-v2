/** Предпочтение темы (система/светлая/тёмная): выбор хранится в localStorage.
 *
 * Инвариант forced-dark (V6): apply() всегда выставляет data-theme="dark"
 * независимо от сохранённого выбора — светлая тема не применяется, путь
 * data-theme="light" недостижим из оболочки. get()/set() осознанно продолжают
 * персистить выбор (зарезервировано под будущую светлую тему), DOM при этом
 * остаётся тёмным. Переключатель в шапке не монтируется (см. settings.spec.ts:
 * [id^='lnt-theme-'] отсутствует). Ничего не знает о бэкенде — локальная настройка. */

export type ThemeChoice = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "lnt-theme";

const CHOICES: readonly ThemeChoice[] = ["system", "light", "dark"];

export interface ThemeController {
  get(): ThemeChoice;
  set(choice: ThemeChoice): void;
  /** Применяет текущий выбор к documentElement (forced-dark: всегда "dark"). */
  apply(): void;
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

  function apply(): void {
    // Forced-dark: светлый путь недостижим — выбор персистится, но не применяется.
    win.document.documentElement.setAttribute("data-theme", "dark");
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
    dispose() {
      media?.removeEventListener?.("change", onMediaChange);
    },
  };
}
