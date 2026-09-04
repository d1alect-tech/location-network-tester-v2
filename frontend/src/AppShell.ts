import "./style.css";
import { LntApiClient } from "./api/client";
import { captureParamsToPrefill } from "./capture/captureDeepLink";
// BEGIN Todo 40: регистрация рабочего процесса захвата (аддитивно, один блок).
import { createCaptureView } from "./capture/captureView";
import type { CaptureViewHandle } from "./capture/captureView";
import { clearElement, el } from "./components/primitives/dom";
import { announcePolite } from "./components/primitives/status";
import { RouteStore } from "./state/routeState";
// END Todo 40
// --- Инспекция V6: единое окно сравнения (полный захват экрана) ---
import "./components/charts/charts.css";
import { type V6ShellHeader, createV6ShellHeader, createV6ShellStatusbar } from "./shell/v6Shell";
import { mountInspectV6 } from "./views/inspect/inspectV6";

// Simple Hash Router
export type Route = "catalog" | "capture" | "inspect" | "experiments" | "reports" | "settings";

export const ROUTES: Record<Route, { title: string; desc: string }> = {
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

import { type ThemeController, createThemePreference } from "./state/themePreference";
// ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
import { mountCatalogWorkspace } from "./views/catalog/catalogWorkspace";
// ===== END T39 CATALOG REGISTRATION =====
// BEGIN Todo 43: рабочая область экспериментов (аддитивно, один блок).
import { mountExperimentsWorkspace } from "./views/experiments/experimentsWorkspace";
// END Todo 43
// BEGIN Todo 44: отчёты, настройки и переключатель темы (аддитивно).
import { mountReportsWorkspace } from "./views/reports/reportsWorkspace";
import { mountSettingsWorkspace } from "./views/settings/settingsWorkspace";
// END Todo 44
// BEGIN Todo 40: общий клиент панели для раздела «Захват».
const shellClient = new LntApiClient();
// END Todo 40

export class AppShell {
  private container: HTMLElement;
  private currentRoute: Route = "catalog";
  private readonly routes: RouteStore;
  private readonly theme: ThemeController;
  private readonly onHashChange: () => void;
  private disposed = false;
  // BEGIN Todo 40
  private captureView: CaptureViewHandle | null = null;
  // END Todo 40
  private v6Header: V6ShellHeader | null = null;

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
    // Тема применяется до первой отрисовки (без вспышки); переключатель в шапке не монтируем.
    this.theme = createThemePreference(window);
    this.onHashChange = (): void => this.handleRoute();
    window.addEventListener("hashchange", this.onHashChange);
  }

  /** Размонтирование: снимает hashchange-подписки и media-наблюдатель темы.
   *  Поведение смонтированной оболочки не меняется — только teardown. */
  public dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    window.removeEventListener("hashchange", this.onHashChange);
    this.routes.dispose();
    this.theme.dispose();
    this.activeViewCleanup?.();
    this.activeViewCleanup = null;
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
    clearElement(this.container);
    this.v6Header = createV6ShellHeader({ activeRoute: this.currentRoute });
    const view = el("div", { className: "view-container", attrs: { id: "view-container" } });
    const main = el("main", { className: "app-main", attrs: { id: "app-main" } }, [view]);
    this.container.append(this.v6Header.root, main, createV6ShellStatusbar().root);
  }

  private handleRoute(): void {
    try {
      const hash = window.location.hash;
      if (!hash.startsWith("#/")) {
        // Redirect to default
        window.location.hash = "#/catalog";
        return;
      }
      // Маршрут и фильтры читаются из модели состояния (safe-restore при перезагрузке).
      this.routes.syncFromUrl();
      const parsed = this.routes.get();
      const route: Route = parsed.route in ROUTES ? (parsed.route as Route) : "catalog";
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
    this.v6Header?.setActiveRoute(this.currentRoute);
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

    // BEGIN Todo 40: маршрут «Захват» монтирует полный рабочий процесс.
    this.captureView?.dispose();
    this.captureView = null;
    // END Todo 40

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

    // BEGIN Todo 43: маршрут «Эксперименты» монтирует полный рабочий контур.
    if (this.currentRoute === "experiments") {
      viewContainer.innerHTML = "";
      viewContainer.className = "view-container lnt-exp-view-container";
      this.activeViewCleanup = mountExperimentsWorkspace(viewContainer as HTMLElement, {
        client: this.apiClient,
        routes: this.routes,
      });
      this.mountedRoute = this.currentRoute;
      return;
    }
    // END Todo 43

    // BEGIN Todo 44: маршруты «Отчёты» и «Настройки» (аддитивно).
    if (this.currentRoute === "reports" || this.currentRoute === "settings") {
      viewContainer.innerHTML = "";
      viewContainer.className = "view-container";
      this.activeViewCleanup =
        this.currentRoute === "reports"
          ? mountReportsWorkspace(viewContainer as HTMLElement, {
              client: this.apiClient,
              routes: this.routes,
            })
          : mountSettingsWorkspace(viewContainer as HTMLElement, { client: this.apiClient });
      this.mountedRoute = this.currentRoute;
      return;
    }
    // END Todo 44

    // BEGIN Todo 40
    if (this.currentRoute === "capture") {
      const view = createCaptureView(shellClient, {
        initial: captureParamsToPrefill(this.routes.get().params),
      });
      this.captureView = view;
      clearElement(viewContainer);
      viewContainer.append(view.root);
      this.mountedRoute = this.currentRoute;
      return;
    }
    // END Todo 40

    // --- Инспекция V6: окно сравнения под общей оболочкой ---
    if (this.currentRoute === "inspect") {
      viewContainer.innerHTML = "";
      viewContainer.className = "view-container";
      let inspectCleanup: (() => void) | null = null;
      let cancelled = false;
      void mountInspectV6(viewContainer as HTMLElement, {
        client: this.apiClient,
        routes: this.routes,
      }).then((cleanup) => {
        if (cancelled) {
          cleanup();
          return;
        }
        inspectCleanup = cleanup;
      });
      this.activeViewCleanup = () => {
        cancelled = true;
        if (inspectCleanup !== null) inspectCleanup();
        inspectCleanup = null;
      };
      this.mountedRoute = this.currentRoute;
      return;
    }

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
        <div class="error-message"></div>
        <button class="btn-recovery" id="btn-recover">Сбросить и вернуться на главную</button>
      </div>
    `;
    // Todo 51 / DEF-005: сообщение об ошибке может содержать данные сервера
    // (detail API) — вставляем только через textContent, никогда в innerHTML.
    const messageNode = main.querySelector(".error-message");
    if (messageNode) messageNode.textContent = error.stack || error.message;

    const btn = main.querySelector("#btn-recover");
    if (btn) {
      btn.addEventListener("click", () => {
        // Clear search query parameter and reset hash
        window.location.href = `${window.location.origin}${window.location.pathname}#/catalog`;
      });
    }
  }
}
