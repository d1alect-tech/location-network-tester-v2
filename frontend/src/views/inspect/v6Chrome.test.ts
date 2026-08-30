import { describe, expect, it, vi } from "vitest";
import { createV6Chrome } from "./v6Chrome";

const NAV_HREFS = [
  "#/catalog",
  "#/capture",
  "#/inspect",
  "#/experiments",
  "#/reports",
  "#/settings",
] as const;

describe("createV6Chrome", () => {
  it("builds a tabbar with the six inspect-shell hashes and no prepare link", () => {
    // Given / When
    const { header } = createV6Chrome({ onCapture: () => undefined });
    const links = [...header.querySelectorAll(".tabbar a")];

    // Then
    expect(links).toHaveLength(6);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([...NAV_HREFS]);
    expect(header.querySelector('a[href="#/prepare"]')).toBeNull();
  });

  it("marks the inspect tab as the current page", () => {
    // Given / When
    const { header } = createV6Chrome({ onCapture: () => undefined });
    const inspect = header.querySelector('a[href="#/inspect"]');

    // Then
    expect(inspect).toBeInstanceOf(HTMLAnchorElement);
    if (!(inspect instanceof HTMLAnchorElement)) return;
    expect(inspect.getAttribute("aria-current")).toBe("page");
    expect(inspect.classList.contains("is-active")).toBe(true);
  });

  it("exposes a capture-form commandbar whose submit button calls onCapture once", () => {
    // Given
    const onCapture = vi.fn();
    const { commandbar } = createV6Chrome({ onCapture });

    // When
    const submit = commandbar.querySelector("button[type=submit]");
    expect(commandbar.getAttribute("data-showcase")).toBe("capture-form");
    expect(submit).toBeInstanceOf(HTMLButtonElement);
    if (!(submit instanceof HTMLButtonElement)) return;
    submit.click();

    // Then
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it("hides the error band until showError and hides it again on hideError", () => {
    // Given
    const { errorBand, showError, hideError } = createV6Chrome({
      onCapture: () => undefined,
    });
    expect(errorBand.hidden).toBe(true);

    // When
    showError("нет сессии");

    // Then
    expect(errorBand.hidden).toBe(false);
    expect(errorBand.textContent).toBe("нет сессии");

    hideError();
    expect(errorBand.hidden).toBe(true);
  });
});
