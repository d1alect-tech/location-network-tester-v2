import "./style.css";

// Simple Hash Router
export type Route = "prepare" | "capture" | "inspect" | "experiments" | "reports" | "settings";

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
};

export class AppShell {
  private container: HTMLElement;
  private currentRoute: Route = "prepare";

  constructor(container: HTMLElement) {
    this.container = container;
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
      let route: Route = "prepare";
      if (hash.startsWith("#/")) {
        const r = hash.slice(2) as Route;
        if (ROUTES[r]) {
          route = r;
        }
      } else {
        // Redirect to default
        window.location.hash = "#/prepare";
        return;
      }

      this.currentRoute = route;
      this.updateActiveNav();
      this.renderView();
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

    // Check for a special test trigger to test error boundary
    if (this.currentRoute === "experiments" && window.location.search.includes("trigger-error")) {
      throw new Error("Тестовая критическая ошибка в представлении Эксперименты");
    }

    const routeInfo = ROUTES[this.currentRoute];
    if (!routeInfo) return;

    viewContainer.innerHTML = `
      <div class="placeholder-view">
        <h2 class="placeholder-title">${routeInfo.title}</h2>
        <p class="placeholder-desc">${routeInfo.desc}</p>
      </div>
    `;
  }

  public renderErrorBoundary(error: Error): void {
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
