import { beforeEach, describe, expect, it } from "vitest";
import { THEME_STORAGE_KEY, createThemePreference } from "./themePreference";

describe("themePreference", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("apply always sets documentElement data-theme to dark", () => {
    const theme = createThemePreference(window);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    theme.dispose();
  });

  it("apply stays dark even after set(light)", () => {
    const theme = createThemePreference(window);
    theme.set("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    theme.dispose();
  });

  it("rejects unknown stored values instead of crashing", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "neon-purple");
    const theme = createThemePreference(window);
    expect(theme.get()).toBe("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    theme.dispose();
  });
});
