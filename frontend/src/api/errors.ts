/** Типизированные ошибки API с компактными русскими сообщениями для UI. */

export type ApiErrorKind =
  | "network"
  | "http"
  | "parse"
  | "conflict"
  | "build_mismatch"
  | "server_restart"
  | "uninitialized";

const RU_MESSAGES: Record<ApiErrorKind, string> = {
  network: "Нет связи с сервером. Проверьте, что панель запущена.",
  http: "Сервер вернул ошибку.",
  parse: "Некорректный ответ сервера.",
  conflict: "Конфликт версий: данные изменены другим процессом.",
  build_mismatch: "Версия интерфейса устарела: перезагрузите страницу.",
  server_restart: "Сервер перезапущен: обновите страницу и повторите действие.",
  uninitialized: "Приложение не инициализировано: перезагрузите страницу.",
};

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly code?: string;

  constructor(
    kind: ApiErrorKind,
    options: { status?: number; code?: string; cause?: unknown; message?: string } = {},
  ) {
    super(options.message ?? RU_MESSAGES[kind], { cause: options.cause });
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status;
    this.code = options.code;
  }
}

/** Разбирает три формы ошибочных ответов бэкенда:
 * {code, detail} | {detail: "строка"} | {detail: {code?, detail?}}. */
export function parseApiError(status: number, body: unknown): ApiError {
  let code: string | undefined;
  let detailText: string | undefined;
  if (typeof body === "object" && body !== null) {
    const record = body as Record<string, unknown>;
    if (typeof record.code === "string") code = record.code;
    const detail = record.detail;
    if (typeof detail === "string") {
      detailText = detail;
    } else if (typeof detail === "object" && detail !== null) {
      const nested = detail as Record<string, unknown>;
      if (typeof nested.code === "string") code = nested.code;
      if (typeof nested.detail === "string") detailText = nested.detail;
    }
  }
  if (status === 403 && code === "mutation_nonce_invalid") {
    return new ApiError("server_restart", { status, code });
  }
  if (status === 409) {
    return new ApiError("conflict", { status, code, cause: detailText });
  }
  return new ApiError("http", { status, code, cause: detailText });
}

/** Приводит произвольную ошибку к ApiError; AbortError проходит насквозь. */
export function normalizeThrown(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (isAbortError(error)) {
    return new ApiError("network", { code: "aborted", cause: error });
  }
  return new ApiError("network", { cause: error });
}

export function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "AbortError"
  );
}
