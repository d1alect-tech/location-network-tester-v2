import { describe, expect, it, vi } from "vitest";
import { createExperimentsTabs } from "./experimentsTabs";

function mountTabs(): ReturnType<typeof createExperimentsTabs> {
  const handle = createExperimentsTabs(
    [
      { key: "overview", label: "Обзор", paneContent: [] },
      { key: "compare", label: "Сравнение", paneContent: [] },
      { key: "trends", label: "Тренды", paneContent: [] },
    ],
    { onFirstAttach: vi.fn(), onSelect: vi.fn() },
  );
  document.body.replaceChildren(handle.tabBar);
  for (const pane of handle.panes.values()) document.body.append(pane);
  handle.select("overview");
  return handle;
}

function tabs(): HTMLButtonElement[] {
  return [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
}

function press(node: HTMLElement, key: string): void {
  node.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

describe("experimentsTabs: паттерн catalog-табов", () => {
  it("начальное состояние: aria-selected и roving tabindex на первом табе", () => {
    // Given / When
    mountTabs();

    // Then
    const [first, second, third] = tabs();
    expect(first?.getAttribute("aria-selected")).toBe("true");
    expect(first?.tabIndex).toBe(0);
    expect(second?.getAttribute("aria-selected")).toBe("false");
    expect(second?.tabIndex).toBe(-1);
    expect(third?.tabIndex).toBe(-1);
  });

  it("табы связаны с панелями через id/aria-controls/aria-labelledby", () => {
    // Given / When
    const handle = mountTabs();

    // Then
    for (const [key, pane] of handle.panes) {
      const tab = document.querySelector(`[data-exp-tab="${key}"]`);
      expect(tab?.getAttribute("aria-controls")).toBe(pane.id);
      expect(pane.getAttribute("aria-labelledby")).toBe(tab?.id);
    }
  });

  it("ArrowRight переводит фокус на следующий таб (как в каталоге)", () => {
    // Given
    mountTabs();
    const [first, second] = tabs();

    // When
    first?.focus();
    press(first as HTMLElement, "ArrowRight");

    // Then
    expect(document.activeElement).toBe(second);
  });

  it("ArrowLeft с первого таба заворачивается на последний", () => {
    // Given
    mountTabs();
    const [first, , third] = tabs();

    // When
    first?.focus();
    press(first as HTMLElement, "ArrowLeft");

    // Then
    expect(document.activeElement).toBe(third);
  });

  it("Home/End переводят фокус на крайние табы", () => {
    // Given
    mountTabs();
    const [first, second, third] = tabs();

    // When / Then
    second?.focus();
    press(second as HTMLElement, "End");
    expect(document.activeElement).toBe(third);
    press(third as HTMLElement, "Home");
    expect(document.activeElement).toBe(first);
  });

  it("select двигает roving tabindex и aria-selected за выбором", () => {
    // Given
    const handle = mountTabs();

    // When
    handle.select("compare");

    // Then
    const [first, second] = tabs();
    expect(second?.getAttribute("aria-selected")).toBe("true");
    expect(second?.tabIndex).toBe(0);
    expect(first?.getAttribute("aria-selected")).toBe("false");
    expect(first?.tabIndex).toBe(-1);
  });
});
