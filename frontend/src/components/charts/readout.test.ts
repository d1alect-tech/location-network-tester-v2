import { describe, expect, it } from "vitest";
import { createReadout } from "./readout";

describe("createReadout: доступная альтернатива курсору", () => {
  it("корень содержит вежливый live-регион", () => {
    // Given / When
    const handle = createReadout("Частота, Гц", "PSD, В²/Гц", [{ label: "A" }]);

    // Then
    expect(handle.root.querySelector('[aria-live="polite"]')).not.toBeNull();
  });

  it("уход курсора объявляется русской строкой", () => {
    // Given
    const handle = createReadout("Частота, Гц", "PSD, В²/Гц", [{ label: "A" }]);

    // When
    handle.update({ xValue: null, values: [] });

    // Then
    expect(handle.root.querySelector('[aria-live="polite"]')?.textContent).toContain(
      "Курсор вне графика",
    );
  });
});
