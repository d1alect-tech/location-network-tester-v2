import { beforeEach, describe, expect, it } from "vitest";
import { THEME_STORAGE_KEY, createThemePreference } from "./themePreference";

describe("themePreference", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("defaults to system and applies a resolved data-theme", () => {
    const theme = createThemePreference(window);
    expect(theme.get()).toBe("system");
    const applied = document.documentElement.getAttribute("data-theme");
    expect(["light", "dark"]).toContain(applied);
    theme.dispose();
  });

  it("persists an explicit choice and survives a new controller (reload)", () => {
    const theme = createThemePreference(window);
    theme.set("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    theme.dispose();

    const reloaded = createThemePreference(window);
    expect(reloaded.get()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    reloaded.dispose();
  });

  it("rejects unknown stored values instead of crashing", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "neon-purple");
    const theme = createThemePreference(window);
    expect(theme.get()).toBe("system");
    theme.dispose();
  });

  it("control reflects state and switching updates resolution", () => {
    const theme = createThemePreference(window);
    const control = theme.control();
    document.body.append(control);
    const dark = control.querySelector<HTMLInputElement>("#lnt-theme-dark");
    expect(dark).not.toBeNull();
    dark!.click();
    dark!.checked = true;
    dark!.dispatchEvent(new Event("change"));
    expect(theme.get()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    theme.dispose();
    control.remove();
  });
});
