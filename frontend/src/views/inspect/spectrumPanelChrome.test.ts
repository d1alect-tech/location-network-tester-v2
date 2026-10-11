import { describe, expect, it } from "vitest";
import { createSpectrumPanelChrome } from "./spectrumPanelChrome";

/** Given / When / Then: каркас сигнального окна собирается в исходном состоянии. */

describe("createSpectrumPanelChrome", () => {
  it("starts on the spectrum view with the status row hidden", () => {
    // Given / When
    const chrome = createSpectrumPanelChrome();

    // Then
    expect(chrome.spectrumBtn.getAttribute("aria-pressed")).toBe("true");
    expect(chrome.gramBtn.getAttribute("aria-pressed")).toBe("false");
    expect(chrome.status.hidden).toBe(true);
    expect(chrome.retryButton.hidden).toBe(false);
    expect(chrome.viewToggle.getAttribute("role")).toBe("group");
    expect(chrome.status.contains(chrome.statusText)).toBe(true);
    expect(chrome.status.contains(chrome.retryButton)).toBe(true);
  });
});
