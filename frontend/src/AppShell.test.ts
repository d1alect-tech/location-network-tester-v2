import { beforeEach, describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

describe("AppShell Router & Error Boundary", () => {
  let container: HTMLElement;
  let appShell: AppShell;

  beforeEach(() => {
    container = document.createElement("div");
    container.id = "app";
    document.body.appendChild(container);
    appShell = new AppShell(container);
  });

  it("should render the app shell with navigation links", () => {
    appShell.init();
    const nav = container.querySelector("nav");
    expect(nav).not.toBeNull();
    const links = container.querySelectorAll(".snav-item");
    expect(links.length).toBe(6);
  });

  it("should render error boundary when an error is thrown", () => {
    appShell.init();
    const error = new Error("Test error message");
    appShell.renderErrorBoundary(error);

    const errorPanel = container.querySelector(".error-panel");
    expect(errorPanel).not.toBeNull();
    expect(errorPanel?.querySelector(".error-title")?.textContent).toBe(
      "Критическая ошибка интерфейса",
    );
    expect(errorPanel?.querySelector(".error-message")?.textContent).toContain(
      "Test error message",
    );
  });

  it("DEF-005: renders hostile payload as inert text, never markup", () => {
    // Given: сообщение об ошибке несёт серверный detail с активной разметкой.
    const payload = '<img src=x onerror="window.__xss=1"><b>injected</b>';

    // When
    appShell.renderErrorBoundary(new Error(payload));

    // Then: разметка не материализуется, текст доступен как textContent.
    expect(container.querySelectorAll("img").length).toBe(0);
    expect(container.querySelectorAll("b").length).toBe(0);
    const message = container.querySelector(".error-message");
    expect(message?.textContent).toContain(payload);
    expect(message?.innerHTML).not.toContain("<img");
    expect(message?.innerHTML).not.toContain("<b>");
  });
});
