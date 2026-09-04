import { describe, expect, it, vi } from "vitest";
import { createV6Chrome } from "./v6Chrome";

describe("createV6Chrome", () => {
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
