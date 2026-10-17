/** Тон баннера восстановления: семантика состояния, а не один красный на всё.
 * Предупреждение (контекст цел, журнал с предупреждением) — янтарный warn;
 * отсутствие контекста — info; красный остаётся у реального повреждения. */

import { describe, expect, it } from "vitest";
import { createRecoveryPanel } from "./contextFieldsView";

describe("createRecoveryPanel: тон по health", () => {
  it("context_valid с предупреждением журнала — warn, не error", () => {
    // Given / When
    const panel = createRecoveryPanel(["context_events_torn_tail"], "context_valid");

    // Then
    expect(panel.classList.contains("banner-warn")).toBe(true);
    expect(panel.classList.contains("banner-info")).toBe(false);
    expect(panel.textContent).toContain(
      "Контекст исправен. Журнал изменений содержит предупреждение.",
    );
  });

  it("context_absent — info-подсказка, не ошибка", () => {
    // Given / When
    const panel = createRecoveryPanel([], "context_absent");

    // Then
    expect(panel.classList.contains("banner-info")).toBe(true);
    expect(panel.classList.contains("banner-warn")).toBe(false);
    expect(panel.textContent).toContain("Контекст сессии ещё не сохранён");
  });

  it("context_invalid — красный error остаётся", () => {
    // Given / When
    const panel = createRecoveryPanel(["context_cache_malformed"], "context_invalid");

    // Then
    expect(panel.classList.contains("banner-warn")).toBe(false);
    expect(panel.classList.contains("banner-info")).toBe(false);
    expect(panel.textContent).toContain("Контекст сессии повреждён");
  });
});
