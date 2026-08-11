export const THEME_KEY = "lnt-theme";

const PREFERENCES = new Set(["system", "light", "dark"]);

export function normalizePreference(value) {
  return PREFERENCES.has(value) ? value : "system";
}

export function resolveTheme(preference, prefersDark) {
  const normalized = normalizePreference(preference);
  if (normalized === "system") {
    return prefersDark ? "dark" : "light";
  }
  return normalized;
}

export function createThemeController({ root, select, storage, media, onChange }) {
  let currentPreference = "system";
  let started = false;

  function applyTheme() {
    root.dataset.theme = resolveTheme(currentPreference, media.matches);
    onChange?.();
  }

  function readPreference() {
    try {
      return normalizePreference(storage.getItem(THEME_KEY));
    } catch (error) {
      if (!(error instanceof DOMException)) {
        throw error;
      }
      return "system";
    }
  }

  function persistPreference() {
    try {
      storage.setItem(THEME_KEY, currentPreference);
    } catch (error) {
      if (!(error instanceof DOMException)) {
        throw error;
      }
      return;
    }
  }

  function handleSelectChange() {
    currentPreference = normalizePreference(select.value);
    applyTheme();
    select.value = currentPreference;
    persistPreference();
  }

  function handleMediaChange() {
    if (currentPreference === "system") {
      applyTheme();
    }
  }

  function start() {
    if (started) {
      return;
    }
    currentPreference = readPreference();
    applyTheme();
    select.value = currentPreference;
    select.addEventListener("change", handleSelectChange);
    media.addEventListener("change", handleMediaChange);
    started = true;
  }

  function stop() {
    if (!started) {
      return;
    }
    select.removeEventListener("change", handleSelectChange);
    media.removeEventListener("change", handleMediaChange);
    started = false;
  }

  return { start, stop };
}
