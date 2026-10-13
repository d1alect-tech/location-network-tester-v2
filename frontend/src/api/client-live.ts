/** Живой режим прибора (routes_live.py): управление с nonce, статус владения
 * и SSE-кадры. Один экземпляр на панель — вкладки «Осциллограф» и «Анализатор»
 * (sa) делят состояние владения и поток. POST /api/live/* — мутации с
 * заголовком запуска (client.requestJson mutation: true); SSE — EventSource
 * с именованными событиями frame/spectrum/heartbeat, родное переподключение, при
 * затишье после сбоя — fallback-опрос GET /api/live/state (паттерн
 * capture/sse.ts). Подписка до старта разрешена: без захвата приходят
 * heartbeat-события со статусом владения. */

import { LntApiClient } from "./client";
import type { RequestOptions } from "./client";
import { ApiError } from "./errors";
import { isLiveFramePayload, isLiveSpectrumPayload, isLiveStatePayload } from "./guards-live";
import type {
  LiveConfigRequest,
  LiveSseDeps,
  LiveStartRequest,
  LiveStatePayload,
  LiveTrigger,
  LiveWatchHandle,
  LiveWatchHandlers,
} from "./types-live";

const FRAMES_PATH = "/api/live/frames";
const DEFAULT_STALE_MS = 4000;

export interface LiveApi {
  /** GET /api/live/state — снимок владения: state и mode — два явных поля. */
  state(options?: RequestOptions): Promise<LiveStatePayload>;
  /** POST /api/live/start — берёт прибор; повторно при живом потоке — 409. */
  start(request: LiveStartRequest, options?: RequestOptions): Promise<LiveStatePayload>;
  /** POST /api/live/stop — освобождает прибор (идемпотентно). */
  stop(options?: RequestOptions): Promise<LiveStatePayload>;
  /** POST /api/live/config — триггер на ходу + опциональный SA-контур. */
  updateConfig(config: LiveConfigRequest, options?: RequestOptions): Promise<LiveStatePayload>;
  /** POST /api/live/config — триггер на ходу, без перезапуска захвата. */
  updateTrigger(trigger: LiveTrigger, options?: RequestOptions): Promise<LiveStatePayload>;
  /** Авто-стоп по правилу маршрутов: POST только если поток считался активным. */
  stopIfActive(options?: RequestOptions): Promise<void>;
  /** Подписка на события frame/heartbeat; один EventSource на вызов. */
  watchFrames(handlers: LiveWatchHandlers, deps?: LiveSseDeps): LiveWatchHandle;
}

/** Группа маршрутов, удерживающих live-поток: уход из неё останавливает
 * поток, смена маршрута внутри группы (scope↔sa) и смена query того же
 * маршрута его сохраняют. Стоп-правило живёт в AppShell. */
export const LIVE_ROUTE_GROUP: ReadonlySet<string> = new Set(["scope", "sa"]);

export function createLiveApi(client: LntApiClient): LiveApi {
  let active = false;

  function applyStatePayload(payload: unknown): LiveStatePayload {
    if (!isLiveStatePayload(payload)) throw new ApiError("parse");
    active = payload.state === "running";
    return payload;
  }

  async function readState(options: RequestOptions): Promise<LiveStatePayload> {
    const payload = await client.requestJson("GET", "/api/live/state", undefined, options);
    return applyStatePayload(payload);
  }

  async function mutate(
    path: string,
    body: unknown,
    options: RequestOptions,
  ): Promise<LiveStatePayload> {
    await client.ensureReady(options);
    const payload = await client.requestJson("POST", path, body, { ...options, mutation: true });
    return applyStatePayload(payload);
  }

  const stop = (options: RequestOptions): Promise<LiveStatePayload> =>
    mutate("/api/live/stop", undefined, options);

  return {
    state: (options = {}) => readState(options),
    start: (request, options = {}) => mutate("/api/live/start", request, options),
    stop,
    updateConfig: (config, options = {}) => mutate("/api/live/config", config, options),
    updateTrigger: (trigger, options = {}) => mutate("/api/live/config", trigger, options),
    stopIfActive: async (options = {}) => {
      if (!active) return;
      await stop(options);
    },
    watchFrames: (handlers, deps = {}) => {
      const Ctor = deps.eventSourceCtor ?? EventSource;
      const setTimeoutFn = deps.setTimeoutFn ?? ((fn, ms) => setTimeout(fn, ms));
      const clearTimeoutFn = deps.clearTimeoutFn ?? ((handle) => clearTimeout(handle as number));
      const staleTimeoutMs = deps.staleTimeoutMs ?? DEFAULT_STALE_MS;

      let closed = false;
      let staleHandle: unknown = null;
      let pollInFlight = false;
      let lastConnection: "live" | "reconnecting" | null = null;

      // jsdom не реализует EventSource — в тестах подставляется фальшивый конструктор.
      const source = new Ctor(FRAMES_PATH);

      function clearStaleTimer(): void {
        if (staleHandle !== null) {
          clearTimeoutFn(staleHandle);
          staleHandle = null;
        }
      }

      function scheduleStalePoll(): void {
        if (closed || staleHandle !== null) return;
        staleHandle = setTimeoutFn(() => {
          staleHandle = null;
          if (closed || pollInFlight) return;
          pollInFlight = true;
          readState({})
            .then((snapshot) => {
              if (!closed) handlers.onState(snapshot);
            })
            .catch(() => {
              // Опрос недоступен — восстановление остаётся родным переподключением
              // EventSource, но деградированное состояние подтверждается повторно
              // (в обход дедупа announce): stale-индикатор остаётся видимым.
              handlers.onConnection("reconnecting");
            })
            .finally(() => {
              pollInFlight = false;
            });
        }, staleTimeoutMs);
      }

      function announce(kind: "live" | "reconnecting"): void {
        // Повторные одинаковые события не дублируются (дедуп объявлений).
        if (lastConnection === kind) return;
        lastConnection = kind;
        handlers.onConnection(kind);
      }

      source.onopen = () => {
        if (closed) return;
        clearStaleTimer();
        announce("live");
      };

      // Бэкенд шлёт именованные события (ServerSentEvent(event="frame"/
      // "spectrum"/"heartbeat"), поэтому подписка через addEventListener:
      // onmessage их не доставляет.
      const onNamedEvent = (event: Event): void => {
        if (closed) return;
        clearStaleTimer();
        let parsed: unknown;
        try {
          parsed = JSON.parse((event as MessageEvent<string>).data);
        } catch {
          return; // некорректный кадр игнорируется, поток продолжается
        }
        if (isLiveFramePayload(parsed)) {
          handlers.onFrame?.(parsed);
          return;
        }
        if (isLiveSpectrumPayload(parsed)) {
          handlers.onSpectrum?.(parsed);
          return;
        }
        if (isLiveStatePayload(parsed)) {
          active = parsed.state === "running";
          handlers.onState(parsed);
        }
      };
      source.addEventListener("frame", onNamedEvent);
      source.addEventListener("spectrum", onNamedEvent);
      source.addEventListener("heartbeat", onNamedEvent);

      source.onerror = () => {
        if (closed) return;
        announce("reconnecting");
        scheduleStalePoll();
      };

      function close(): void {
        if (closed) return;
        closed = true;
        clearStaleTimer();
        source.close();
      }

      return { close };
    },
  };
}

let shared: LiveApi | null = null;

/** Единственный live-клиент панели: общий для инструментальных вкладок и
 * стоп-правила AppShell — состояние владения не дублируется между вкладками. */
export function sharedLiveApi(): LiveApi {
  if (shared === null) shared = createLiveApi(new LntApiClient());
  return shared;
}

/** Тестовая перевязка singleton-клиента (vitest): новый экземпляр поверх
 * стаб-феча, состояние владения сбрасывается. */
export function rebindSharedLiveApi(client: LntApiClient): LiveApi {
  shared = createLiveApi(client);
  return shared;
}
