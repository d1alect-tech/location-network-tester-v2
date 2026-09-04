import { beforeEach, describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

/**
 * Базовый характеризационный тест: фиксирует наблюдаемое поведение AppShell.
 * С todo 39 в ROUTES добавлен раздел «Каталог» — ссылок стало семь;
 * остальные гарантии маршрутизации сохранены дословно.
 * T5: маршрут «Каталог» монтирует настоящий воркспейс (.lnt-cat-workspace),
 * плейсхолдер-заглушка удалена — фолбэк-тесты следуют новой реальности.
 */
describe("AppShell (baseline characterization)", () => {
  let container: HTMLElement;

  beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState(null, "", "/");
    window.location.hash = "";
    container = document.createElement("div");
    container.id = "app";
    document.body.appendChild(container);
  });

  it("renders six navigation links matching V6 tabbar", () => {
    const shell = new AppShell(container);
    shell.init();
    const links = container.querySelectorAll<HTMLAnchorElement>(".snav-item");
    expect(links.length).toBe(6);
    expect(container.querySelector("#nav-capture")).not.toBeNull();
    expect(container.querySelector("#nav-catalog")).not.toBeNull();
    expect(links[0]?.href).toMatch(/#\/catalog$/);
  });

  it("renders the route view synchronously for a preset hash", () => {
    window.location.hash = "#/capture";
    const shell = new AppShell(container);
    shell.init();
    // Todo 40: маршрут «Захват» намеренно монтирует полный рабочий процесс
    // вместо заглушки (базлайн зафиксирован зелёным до изменений).
    expect(container.querySelector(".capture-view")).not.toBeNull();
    expect(container.querySelector(".view-title")?.textContent).toBe("Захват");
    const active = container.querySelector('[aria-current="page"]');
    expect(active?.getAttribute("data-route")).toBe("capture");
  });

  it("redirects an empty hash to #/catalog and renders the default view", async () => {
    const shell = new AppShell(container);
    shell.init();
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 0);
    });
    expect(window.location.hash).toBe("#/catalog");
    expect(container.querySelector(".lnt-cat-workspace")).not.toBeNull();
  });

  it("redirects the killed legacy #/prepare to #/capture and renders capture (A3)", () => {
    window.location.hash = "#/prepare";
    const shell = new AppShell(container);
    shell.init();
    expect(window.location.hash).toBe("#/capture");
    expect(container.querySelector(".capture-view")).not.toBeNull();
    expect(container.querySelector('[aria-current="page"]')?.getAttribute("data-route")).toBe(
      "capture",
    );
  });

  it("falls back to the default view for an unknown route and keeps the hash", () => {
    window.location.hash = "#/unknown";
    const shell = new AppShell(container);
    shell.init();
    expect(container.querySelector(".lnt-cat-workspace")).not.toBeNull();
    expect(window.location.hash).toBe("#/unknown");
  });

  it("renders the error boundary with an alert role and Russian recovery action", () => {
    const shell = new AppShell(container);
    shell.init();
    shell.renderErrorBoundary(new Error("Тестовая критическая ошибка"));
    const panel = container.querySelector(".error-panel");
    expect(panel?.getAttribute("role")).toBe("alert");
    expect(container.querySelector(".error-title")?.textContent).toBe(
      "Критическая ошибка интерфейса",
    );
    expect(container.querySelector(".error-message")?.textContent).toContain(
      "Тестовая критическая ошибка",
    );
    const button = container.querySelector<HTMLButtonElement>("#btn-recover");
    expect(button?.textContent).toBe("Сбросить и вернуться на главную");
  });

  it("routes the trigger-error experiment view into the error boundary", () => {
    window.history.replaceState(null, "", "/?trigger-error");
    window.location.hash = "#/experiments";
    const shell = new AppShell(container);
    shell.init();
    expect(container.querySelector(".error-panel")).not.toBeNull();
    expect(container.querySelector(".error-message")?.textContent).toContain(
      "Тестовая критическая ошибка в представлении Эксперименты",
    );
  });
});
