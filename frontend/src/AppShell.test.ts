import { beforeEach, describe, expect, it } from "vitest";
import { AppShell, ROUTES } from "./AppShell";

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
    const links = container.querySelectorAll(".nav-link");
    expect(links.length).toBe(Object.keys(ROUTES).length);
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
});
