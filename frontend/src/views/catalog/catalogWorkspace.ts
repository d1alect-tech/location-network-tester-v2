/** Рабочая область каталога (Todo 39): слева панель фильтров и виртуализованный
 * список, справа вкладки «Инспектор контекста» / «Профили». Фильтры живут в
 * параметрах маршрута; запросы обрываются при смене фильтров; выбор сессии
 * тоже отражается в URL и переживает перезагрузку. */

import type { LntApiClient } from "../../api/client";
import { el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import type { RouteStore } from "../../state/routeState";
import { type CatalogFilterPanelHandle, createCatalogFilterPanel } from "./catalogFilterPanel";
import { type CatalogListHandle, createCatalogListView } from "./catalogListView";
import { CatalogStore } from "./catalogStore";
import { type ContextInspectorHandle, createContextInspector } from "./contextInspector";
import { type ProfileManagerHandle, createProfileManager } from "./profileManager";
import { createProfilePreview } from "./profilePreview";
import "./catalog.css";

const QUERY_DEBOUNCE_MS = 150;

/** Ключи параметров URL, отвечающие за фильтры (смена selection не пересчитывает выдачу). */
const FILTER_KEYS = [
  "health",
  "session_type",
  "label",
  "created_from",
  "created_to",
  "profile",
  "tag",
] as const;

export const EMPTY_MESSAGE =
  "По запросу ничего не найдено. Измените параметры фильтрации или нажмите «Сбросить».";
export const LOADING_MESSAGE = "Загрузка списка сессий…";

export interface CatalogWorkspaceOptions {
  client: LntApiClient;
  routes: RouteStore;
}

function catalogQueryFromParams(params: Record<string, string>): Record<string, string> {
  const query: Record<string, string> = {};
  for (const key of [
    "health",
    "session_type",
    "label",
    "created_from",
    "created_to",
    "profile",
    "tag",
  ]) {
    const value = params[key];
    if (value) query[key] = value;
  }
  return query;
}

export function mountCatalogWorkspace(
  container: HTMLElement,
  options: CatalogWorkspaceOptions,
): () => void {
  const { client, routes } = options;

  const store = new CatalogStore((query, signal) =>
    client.catalogSessions({ ...query, page_size: 200 }, { signal }),
  );
  const filterPanel: CatalogFilterPanelHandle = createCatalogFilterPanel({
    store: routes,
    storage: window.localStorage,
  });
  const list: CatalogListHandle = createCatalogListView({
    onActivate: (session) => void activate(session.id),
    onLoadMore: () => void store.loadMore(),
    onRetry: () => void rerun(),
  });
  const inspector: ContextInspectorHandle = createContextInspector({ client });
  const preview = createProfilePreview();

  // Вкладки правой панели.
  const inspectorPanel = el(
    "div",
    { attrs: { role: "tabpanel", "aria-label": "Инспектор контекста" } },
    [inspector.root],
  );
  const profilesHost = el("div", {});
  const profilesPanel = el(
    "div",
    { attrs: { role: "tabpanel", "aria-label": "Профили" }, className: "lnt-cat-profiles-panel" },
    [profilesHost, preview.root],
  );
  profilesPanel.hidden = true;

  const tabButtons: HTMLButtonElement[] = [];
  function makeTab(labelText: string): HTMLButtonElement {
    const button = el("button", {
      className: "lnt-btn lnt-cat-tab",
      text: labelText,
      attrs: { type: "button", role: "tab" },
    });
    button.addEventListener("click", () => selectTab(button));
    button.addEventListener("keydown", (event) => {
      const index = tabButtons.indexOf(button);
      if (event.key === "ArrowRight") {
        event.preventDefault();
        tabButtons[(index + 1) % tabButtons.length]?.focus();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        tabButtons[(index - 1 + tabButtons.length) % tabButtons.length]?.focus();
      }
    });
    tabButtons.push(button);
    return button;
  }
  const inspectorTab = makeTab("Инспектор");
  const profilesTab = makeTab("Профили");
  function selectTab(active: HTMLButtonElement): void {
    for (const button of tabButtons) {
      const isActive = button === active;
      button.setAttribute("aria-selected", isActive ? "true" : "false");
      button.classList.toggle("lnt-cat-tab-active", isActive);
    }
    inspectorPanel.hidden = active !== inspectorTab;
    profilesPanel.hidden = active !== profilesTab;
  }

  const profileManager: ProfileManagerHandle = createProfileManager({
    client,
    onCombinationChange: (combination) => preview.setCombination(combination),
  });
  profilesHost.append(profileManager.root);

  const tabBar = el(
    "div",
    { className: "lnt-cat-tabs", attrs: { role: "tablist", "aria-label": "Правая панель" } },
    [inspectorTab, profilesTab],
  );
  const rightPane = el("div", { className: "lnt-cat-right" }, [
    tabBar,
    inspectorPanel,
    profilesPanel,
  ]);
  const leftPane = el("div", { className: "lnt-cat-left" }, [
    el("h2", { className: "placeholder-title", text: "Каталог" }),
    filterPanel.root,
    list.root,
  ]);
  const root = el("div", { className: "lnt-cat-workspace" }, [leftPane, rightPane]);
  container.append(root);

  async function activate(sessionId: string): Promise<void> {
    list.setSelected(sessionId);
    routes.replaceParams({ session: sessionId });
    ensureSessionLoaded(sessionId);
  }

  let queryTimer: ReturnType<typeof setTimeout> | null = null;
  function scheduleQuery(): void {
    if (queryTimer !== null) clearTimeout(queryTimer);
    queryTimer = setTimeout(() => {
      queryTimer = null;
      void rerun();
    }, QUERY_DEBOUNCE_MS);
  }

  async function rerun(): Promise<void> {
    await store.applyQuery(catalogQueryFromParams(routes.get().params));
  }

  const unsubscribeStore = store.subscribe((state) => {
    if (state.status === "loading" && state.items.length === 0) {
      list.setNotice("loading", LOADING_MESSAGE);
      return;
    }
    if (state.status === "error") {
      list.setNotice("error", state.error ?? "Ошибка загрузки.");
      return;
    }
    if (state.items.length === 0) {
      list.setNotice("empty", EMPTY_MESSAGE);
      return;
    }
    list.clearNotice();
    list.setItems(state.items);
    list.setHasMore(state.nextCursor !== null);
  });

  let lastLoadedId: string | null = null;
  let lastFilterSignature = FILTER_KEYS.map((key) => routes.get().params[key] ?? "").join("\u0001");

  /** Единая точка загрузки контекста: один вызов на идентификатор.
   * Повторные hashchange и двойная активация не перечитывают заново
   * и не затирают правки пользователя посреди редактирования. */
  let loadedSessionId: string | null = null;
  let inFlightSessionId: string | null = null;
  function ensureSessionLoaded(sessionId: string): void {
    if (sessionId === loadedSessionId || sessionId === inFlightSessionId) return;
    inFlightSessionId = sessionId;
    list.setSelected(sessionId);
    void inspector
      .loadSession(sessionId)
      .then(() => {
        loadedSessionId = sessionId;
        announcePolite(`Сессия ${sessionId} открыта`);
      })
      .finally(() => {
        inFlightSessionId = null;
      });
  }

  const unsubscribeRoutes = routes.subscribe(() => {
    filterPanel.syncFromRoute();
    // Перезапрос нужен только при изменении ФИЛЬТРОВ; выбор сессии меняет
    // лишь параметр session и не должен сбрасывать список.
    const signature = FILTER_KEYS.map((key) => routes.get().params[key] ?? "").join("\u0001");
    if (signature !== lastFilterSignature) {
      lastFilterSignature = signature;
      scheduleQuery();
    }
    const sessionId = routes.get().params.session;
    if (sessionId && sessionId !== lastLoadedId) {
      ensureSessionLoaded(sessionId);
      lastLoadedId = sessionId;
    }
  });

  selectTab(inspectorTab);
  filterPanel.syncFromRoute();
  void rerun().then(() => {
    const sessionId = routes.get().params.session;
    if (sessionId) {
      ensureSessionLoaded(sessionId);
      lastLoadedId = sessionId;
    }
  });

  return () => {
    unsubscribeStore();
    unsubscribeRoutes();
    if (queryTimer !== null) clearTimeout(queryTimer);
  };
}
