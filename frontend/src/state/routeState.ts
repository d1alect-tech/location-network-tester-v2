/** Модель маршрута рабочей области: hash-URL с query-фильтрами.
 * Перезагрузка восстанавливает безопасное состояние; секреты (nonce)
 * в URL никогда не попадают — они живут только в памяти клиента. */

export const WORKSPACE_ROUTES = [
  "prepare",
  "catalog",
  "capture",
  "inspect",
  "experiments",
  "reports",
  "settings",
] as const;

export type WorkspaceRoute = (typeof WORKSPACE_ROUTES)[number];

export const DEFAULT_ROUTE: WorkspaceRoute = "catalog";

export interface WorkspaceLocation {
  route: WorkspaceRoute;
  params: Record<string, string>;
}

const SECRET_PARAM_KEYS = new Set(["nonce", "token", "secret", "mutation_nonce", "password"]);

/** Убирает секретоподобные ключи из параметров URL. */
export function sanitizeParams(params: Record<string, string>): Record<string, string> {
  const clean: Record<string, string> = {};
  for (const [key, value] of Object.entries(params)) {
    if (!SECRET_PARAM_KEYS.has(key.toLowerCase())) clean[key] = value;
  }
  return clean;
}

/** Разбирает "#/route?key=value"; неизвестный маршрут → null. */
export function parseHash(hash: string): WorkspaceLocation | null {
  if (!hash.startsWith("#/")) return null;
  const rest = hash.slice(2);
  const queryIndex = rest.indexOf("?");
  const routePart = queryIndex === -1 ? rest : rest.slice(0, queryIndex);
  const queryString = queryIndex === -1 ? "" : rest.slice(queryIndex + 1);
  if (!(WORKSPACE_ROUTES as readonly string[]).includes(routePart)) return null;
  const params: Record<string, string> = {};
  for (const [key, value] of new URLSearchParams(queryString)) params[key] = value;
  return { route: routePart as WorkspaceRoute, params: sanitizeParams(params) };
}

/** Собирает канонический hash; секретные ключи отбрасываются. */
export function serializeLocation(location: WorkspaceLocation): string {
  const search = new URLSearchParams(sanitizeParams(location.params)).toString();
  return search ? `#/${location.route}?${search}` : `#/${location.route}`;
}

type RouteListener = (location: WorkspaceLocation) => void;

export class RouteStore {
  private location: WorkspaceLocation;
  private readonly listeners = new Set<RouteListener>();
  private readonly win: Window;

  constructor(win: Window = window) {
    this.win = win;
    this.location = this.readLocation();
    win.addEventListener("hashchange", () => {
      this.syncFromUrl();
    });
  }

  get(): WorkspaceLocation {
    return this.location;
  }

  subscribe(listener: RouteListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  navigate(location: WorkspaceLocation): void {
    this.win.location.hash = serializeLocation(location);
  }

  /** Сливает фильтры с текущим маршрутом и переходит. */
  replaceParams(params: Record<string, string>): void {
    this.navigate({ route: this.location.route, params: { ...this.location.params, ...params } });
  }

  /** Перечитывает URL; вызывается по hashchange (перезагрузка/назад). */
  syncFromUrl(): void {
    const next = this.readLocation();
    if (
      next.route === this.location.route &&
      Object.entries(next.params).toString() === Object.entries(this.location.params).toString()
    ) {
      return;
    }
    this.location = next;
    for (const listener of this.listeners) listener(next);
  }

  private readLocation(): WorkspaceLocation {
    return parseHash(this.win.location.hash) ?? { route: DEFAULT_ROUTE, params: {} };
  }
}
