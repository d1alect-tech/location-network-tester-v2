import { beforeEach, describe, expect, it } from "vitest";
import { AppShell, ROUTES } from "./AppShell";

/**
 * Базовый характеризационный тест: фиксирует наблюдаемое поведение AppShell.
 * С todo 39 в ROUTES добавлен раздел «Каталог» — ссылок стало семь;
 * остальные гарантии маршрутизации сохранены дословно.
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

  it("renders seven navigation links matching ROUTES", () => {
    const shell = new AppShell(container);
    shell.init();
    const links = container.querySelectorAll<HTMLAnchorElement>(".nav-link");
    expect(links.length).toBe(Object.keys(ROUTES).length);
    expect(links.length).toBe(7);
    expect(container.querySelector("#nav-capture")?.textContent).toBe("Захват");
    expect(container.querySelector("#nav-catalog")?.textContent).toBe("Каталог");
    expect(links[0]?.getAttribute("href")).toBe("#/prepare");
  });

  it("renders the route view synchronously for a preset hash", () => {
    window.location.hash = "#/capture";
    const shell = new AppShell(container);
    shell.init();
    // Todo 40: маршрут «Захват» намеренно монтирует полный рабочий процесс
    // вместо заглушки (базлайн зафиксирован зелёным до изменений).
    expect(container.querySelector(".capture-view")).not.toBeNull();
    expect(container.querySelector(".view-title")?.textContent).toBe("Захват");
    const active = container.querySelector(".nav-link.active");
    expect(active?.getAttribute("data-route")).toBe("capture");
  });

  it("redirects an empty hash to #/catalog and renders the default view", async () => {
    const shell = new AppShell(container);
    shell.init();
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 0);
    });
    expect(window.location.hash).toBe("#/catalog");
    expect(container.querySelector(".placeholder-title")?.textContent).toBe("Каталог");
  });

  it("falls back to the default view for an unknown route and keeps the hash", () => {
    window.location.hash = "#/unknown";
    const shell = new AppShell(container);
    shell.init();
    expect(container.querySelector(".placeholder-title")?.textContent).toBe("Каталог");
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
