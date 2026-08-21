import "./style.css";
import { announcePolite } from "./components/primitives/status";
import { RouteStore } from "./state/routeState";

// Simple Hash Router
export type Route =
  | "prepare"
  | "catalog"
  | "capture"
  | "inspect"
  | "experiments"
  | "reports"
  | "settings";

export const ROUTES: Record<Route, { title: string; desc: string }> = {
  prepare: {
    title: "Подготовка",
    desc: "Выбор профилей оборудования, калибровки, параметров входа CH1/CH2.",
  },
  capture: {
    title: "Захват",
    desc: "Запуск одиночных или серийных измерений, отображение активной задачи.",
  },
  inspect: {
    title: "Инспекция",
    desc: "Детальный анализ выбранной сессии, просмотр спектра мощности (PSD).",
  },
  experiments: {
    title: "Эксперименты",
    desc: "Группировка сессий по протоколам (A/B, A/B/A, повторные серии).",
  },
  reports: {
    title: "Отчёты",
    desc: "Генерация научных отчетов с полной прослеживаемостью (provenance).",
  },
  settings: {
    title: "Настройки",
    desc: "Управление путями сессий, базами данных, резервным копированием.",
  },
  // ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
  catalog: {
    title: "Каталог",
    desc: "Поиск и фильтрация сессий, инспектор контекста, управление профилями.",
  },
  // ===== END T39 CATALOG REGISTRATION =====
};

import { LntApiClient } from "./api/client";
// ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
import { mountCatalogWorkspace } from "./views/catalog/catalogWorkspace";
// ===== END T39 CATALOG REGISTRATION =====

export class AppShell {
  private container: HTMLElement;
  private currentRoute: Route = "prepare";
  private readonly routes: RouteStore;

  // ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
  /** Смонтированное представление и его очистка; смена фильтров внутри
   * одного маршрута не должна пересоздавать рабочую область. */
  private mountedRoute: Route | null = null;
  private activeViewCleanup: (() => void) | null = null;
  private readonly apiClient = new LntApiClient();
  // ===== END T39 CATALOG REGISTRATION =====

  constructor(container: HTMLElement) {
    this.container = container;
    this.routes = new RouteStore(window);
    window.addEventListener("hashchange", () => this.handleRoute());
  }

  public init(): void {
    try {
      this.renderShell();
      this.handleRoute();
    } catch (error) {
      this.renderErrorBoundary(error as Error);
    }
  }

  private renderShell(): void {
    this.container.innerHTML = `
      <header class="app-header">
        <h1 class="app-title">LNT v2</h1>
        <nav class="app-nav" role="navigation">
          ${Object.entries(ROUTES)
            .map(
              ([key, value]) => `
            <a href="#/${key}" class="nav-link" id="nav-${key}" data-route="${key}">${value.title}</a>
          `,
            )
            .join("")}
        </nav>
      </header>
      <main class="app-main" id="app-main">
        <div class="view-container" id="view-container"></div>
      </main>
    `;
  }

  private handleRoute(): void {
    try {
      const hash = window.location.hash;
      if (!hash.startsWith("#/")) {
        // Redirect to default
        window.location.hash = "#/prepare";
        return;
      }
      // Маршрут и фильтры читаются из модели состояния (safe-restore при перезагрузке).
      this.routes.syncFromUrl();
      const parsed = this.routes.get();
      const route: Route = parsed.route in ROUTES ? (parsed.route as Route) : "prepare";
      if (route !== this.currentRoute) {
        announcePolite(`Раздел: ${ROUTES[route].title}`);
      }
      this.currentRoute = route;
      this.updateActiveNav();
      // ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
      // Пересоздаём представление только при смене маршрута: смена фильтров
      // или выбор сессии меняют query того же hash-маршрута.
      if (route !== this.mountedRoute) {
        this.renderView();
      }
      // ===== END T39 CATALOG REGISTRATION =====
    } catch (error) {
      this.renderErrorBoundary(error as Error);
    }
  }

  private updateActiveNav(): void {
    const links = this.container.querySelectorAll(".nav-link");
    for (const link of links) {
      const route = link.getAttribute("data-route");
      if (route === this.currentRoute) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    }
  }

  private renderView(): void {
    const viewContainer = this.container.querySelector("#view-container");
    if (!viewContainer) return;

    this.activeViewCleanup?.();
    this.activeViewCleanup = null;

    // Check for a special test trigger to test error boundary
    if (this.currentRoute === "experiments" && window.location.search.includes("trigger-error")) {
      throw new Error("Тестовая критическая ошибка в представлении Эксперименты");
    }

    const routeInfo = ROUTES[this.currentRoute];
    if (!routeInfo) return;

    // ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
    if (this.currentRoute === "catalog") {
      viewContainer.innerHTML = "";
      viewContainer.className = "view-container lnt-cat-view-container";
      this.activeViewCleanup = mountCatalogWorkspace(viewContainer as HTMLElement, {
        client: this.apiClient,
        routes: this.routes,
      });
      this.mountedRoute = this.currentRoute;
      return;
    }
    // ===== END T39 CATALOG REGISTRATION =====

    viewContainer.innerHTML = `
      <div class="placeholder-view">
        <h2 class="placeholder-title">${routeInfo.title}</h2>
        <p class="placeholder-desc">${routeInfo.desc}</p>
      </div>
    `;
    this.mountedRoute = this.currentRoute;
  }

  public renderErrorBoundary(error: Error): void {
    // ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
    // Граница ошибки сбрасывает смонтированное представление.
    this.mountedRoute = null;
    // ===== END T39 CATALOG REGISTRATION =====
    const main = this.container.querySelector("#app-main") || this.container;
    main.innerHTML = `
      <div class="error-panel" role="alert">
        <h2 class="error-title">Критическая ошибка интерфейса</h2>
        <p>Произошел сбой при отрисовке или маршрутизации представления. Пожалуйста, попробуйте восстановить сессию.</p>
        <div class="error-message">${error.stack || error.message}</div>
        <button class="btn-recovery" id="btn-recover">Сбросить и вернуться на главную</button>
      </div>
    `;

    const btn = main.querySelector("#btn-recover");
    if (btn) {
      btn.addEventListener("click", () => {
        // Clear search query parameter and reset hash
        window.location.href = `${window.location.origin}${window.location.pathname}#/prepare`;
      });
    }
  }
}
