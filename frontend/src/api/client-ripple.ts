/** Под-клиент ripple-артефакта сессии (routes_ripple.py): GET без параметров,
 * без nonce (read-only). Ответ 200 — сохранённые байты сайдкара: разбор
 * JSON и строгий guard v1. Отказы маршрута типизированы машинными кодами:
 * 404 not_built / 404 not_found / 409 reason / 422 / сеть / parse. Феч
 * идёт через client.rawFetch (инъекция тестов), потому что конверт ошибок
 * ripple несёт поле «reason», которое общий parseApiError не извлекает. */

import type { LntApiClient, RequestOptions } from "./client";
import { isAbortError } from "./errors";
import { isRippleArtifact } from "./guards-ripple";
import type { RippleArtifactPayload, RippleConflictReason, RippleErrorKind } from "./types-ripple";

const CONFLICT_REASONS: readonly string[] = [
  "corrupt",
  "schema_incompatible",
  "stale_input",
  "unsafe_sidecar",
];

const RU_MESSAGES: Record<RippleErrorKind, string> = {
  not_built: "Ripple-артефакт не построен для этой сессии: сначала запустите анализ.",
  not_found: "Сессия не найдена.",
  conflict: "Ripple-артефакт не согласован с сессией (повреждён, устарел или схема несовместима).",
  invalid_request: "Некорректный запрос ripple-артефакта.",
  network: "Нет связи с сервером. Проверьте, что панель запущена.",
  parse: "Ripple-артефакт не проходит схему v1.",
  http: "Сервер вернул ошибку.",
};

/** Типизированный отказ ripple-клиента: kind — машина, detail — серверный
 * текст, reason — машинный код 409, когда маршрут его прислал. */
export class RippleApiError extends Error {
  readonly kind: RippleErrorKind;
  readonly status?: number;
  readonly detail?: string;
  readonly reason?: RippleConflictReason;

  constructor(
    kind: RippleErrorKind,
    options: {
      status?: number;
      detail?: string;
      reason?: RippleConflictReason;
      cause?: unknown;
    } = {},
  ) {
    super(RU_MESSAGES[kind], { cause: options.cause });
    this.name = "RippleApiError";
    this.kind = kind;
    this.status = options.status;
    this.detail = options.detail;
    this.reason = options.reason;
  }
}

export interface RippleApi {
  /** GET /api/sessions/{id}/ripple — сохранённый сайдкар v1, проверенный
   * гвардом; вычислений и мутаций на клиенте нет. */
  artifact(sessionId: string, options?: RequestOptions): Promise<RippleArtifactPayload>;
}

function ripplePath(sessionId: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}/ripple`;
}

/** Читает конверт ошибок маршрута: {detail, reason} — оба опциональны,
 * тело может быть вовсе без JSON. */
async function readErrorEnvelope(response: Response): Promise<{
  detail: string | undefined;
  reason: string | undefined;
}> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { detail: undefined, reason: undefined };
  }
  if (typeof body !== "object" || body === null) {
    return { detail: undefined, reason: undefined };
  }
  const record = body as Record<string, unknown>;
  const detail = typeof record.detail === "string" ? record.detail : undefined;
  const reason = typeof record.reason === "string" ? record.reason : undefined;
  return { detail, reason };
}

function rippleHttpError(
  status: number,
  envelope: { detail?: string; reason?: string },
): RippleApiError {
  if (status === 404) {
    if (envelope.reason === "not_built") {
      return new RippleApiError("not_built", { status, detail: envelope.detail });
    }
    return new RippleApiError("not_found", { status, detail: envelope.detail });
  }
  if (status === 409) {
    // Неизвестный серверу код причины не теряет статус и detail: узнавание
    // кода — сужение, а не подмена.
    const reason = CONFLICT_REASONS.includes(envelope.reason as string)
      ? (envelope.reason as RippleConflictReason)
      : undefined;
    return new RippleApiError("conflict", { status, detail: envelope.detail, reason });
  }
  if (status === 422) {
    return new RippleApiError("invalid_request", { status, detail: envelope.detail });
  }
  return new RippleApiError("http", { status, detail: envelope.detail });
}

export function createRippleApi(client: LntApiClient): RippleApi {
  async function artifact(
    sessionId: string,
    options: RequestOptions = {},
  ): Promise<RippleArtifactPayload> {
    let response: Response;
    try {
      response = await client.rawFetch(ripplePath(sessionId), {
        method: "GET",
        signal: options.signal,
      });
    } catch (error) {
      if (isAbortError(error)) throw error;
      throw new RippleApiError("network", { cause: error });
    }
    if (!response.ok) {
      const envelope = await readErrorEnvelope(response);
      throw rippleHttpError(response.status, envelope);
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch (error) {
      throw new RippleApiError("parse", { cause: error });
    }
    if (!isRippleArtifact(payload)) throw new RippleApiError("parse");
    return payload;
  }

  return { artifact };
}
