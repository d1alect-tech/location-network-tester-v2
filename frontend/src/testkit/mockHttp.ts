/** Мини-HTTP для единого мок-бэкенда: предикат путей и ответы-объекты.
 * Хранилища возвращают MockHttpReply | null (null — «не мой маршрут»);
 * точка входа превращает reply в route.fulfill. Без зависимости Playwright,
 * чтобы чистую логику покрывал vitest. */

export interface MockHttpRequest {
  method: string;
  path: string;
  searchParams: URLSearchParams;
  nonceOk: boolean;
  bodyJson<T>(): T;
}

export interface MockHttpReply {
  status: number;
  body?: unknown;
  contentType?: string;
}

/** Точный предикат вместо glob "**\/api/**": тот матчил и модули vite вида
 * /static/v2/src/api/*.ts и ломал загрузку приложения JSON-ответом. */
export function isApiPath(pathname: string): boolean {
  return pathname.startsWith("/api/") || pathname === "/api" || pathname.includes("!/api/");
}

/** Срезает префикс сборки: приложение ходит под /static/v2/. */
export function stripStaticPrefix(pathname: string): string {
  return pathname.replace(/^\/static\/v2/, "");
}

export function ok(body: unknown): MockHttpReply {
  return { status: 200, body };
}

export function created(body: unknown): MockHttpReply {
  return { status: 201, body };
}

export function accepted(body: unknown): MockHttpReply {
  return { status: 202, body };
}

export function failure(status: number, body: unknown): MockHttpReply {
  return { status, body };
}

export function notFound(detail: string): MockHttpReply {
  return { status: 404, body: { detail } };
}

export function nonceRejected(): MockHttpReply {
  return { status: 403, body: { code: "mutation_nonce_invalid", detail: "нет nonce" } };
}
