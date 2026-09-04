import { describe, expect, it, vi } from "vitest";
import { errorWithRetry } from "./stateViews";

describe("errorWithRetry", () => {
  it("показывает русское сообщение об ошибке и кнопку повтора", () => {
    // Given
    const onRetry = vi.fn();

    // When
    const node = errorWithRetry("Не удалось загрузить список экспериментов.", onRetry);

    // Then
    expect(node.querySelector("[role=alert]")?.textContent).toContain(
      "Не удалось загрузить список экспериментов.",
    );
    const button = node.querySelector("button");
    expect(button?.textContent).toContain("Повторить");
    button?.click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("кнопка повтора — .lnt-btn (цель 44px из примитивов)", () => {
    // Given / When
    const node = errorWithRetry("Ошибка.", () => undefined);

    // Then
    expect(node.querySelector("button")?.classList.contains("lnt-btn")).toBe(true);
  });
});
