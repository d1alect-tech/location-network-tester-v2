/** Транспорт SSE задачи: EventSource напрямую против /api/jobs/{id}/events
 * (заголовки для SSE не нужны; nonce — только для мутаций). Переподключение
 * родное для EventSource; при затишье — опрос GET /api/jobs/{id} как fallback.
 * Планировщики внедряются: тесты идут на fake timers. */

import { isJobSnapshot } from "../api/guards-jobs";
import type { JobSnapshot } from "../api/types-jobs";

export interface SseDeps {
  eventSourceCtor?: typeof EventSource;
  setTimeoutFn?: (handler: () => void, timeout: number) => unknown;
  clearTimeoutFn?: (handle: unknown) => void;
  /** Fallback-опрос снимка при затишье потока (например jobs.get). */
  pollSnapshot?: () => Promise<JobSnapshot>;
  /** Сколько мс ждать событий после сбоя до fallback-опроса. */
  staleTimeoutMs?: number;
}

export interface WatchHandlers {
  onSnapshot(snapshot: JobSnapshot): void;
  onConnection(kind: "live" | "reconnecting"): void;
}

export interface WatchHandle {
  close(): void;
}

const DEFAULT_STALE_MS = 4000;

export function watchJobEvents(
  jobId: string,
  handlers: WatchHandlers,
  deps: SseDeps = {},
): WatchHandle {
  const Ctor = deps.eventSourceCtor ?? EventSource;
  const setTimeoutFn = deps.setTimeoutFn ?? ((fn, ms) => setTimeout(fn, ms));
  const clearTimeoutFn = deps.clearTimeoutFn ?? ((handle) => clearTimeout(handle as number));
  const staleTimeoutMs = deps.staleTimeoutMs ?? DEFAULT_STALE_MS;

  let closed = false;
  let staleHandle: unknown = null;
  let pollInFlight = false;
  let lastConnection: "live" | "reconnecting" | null = null;

  // jsdom не реализует EventSource — в тестах подставляется фальшивый конструктор.
  const source = new Ctor(`/api/jobs/${encodeURIComponent(jobId)}/events`);

  function clearStaleTimer(): void {
    if (staleHandle !== null) {
      clearTimeoutFn(staleHandle);
      staleHandle = null;
    }
  }

  function scheduleStalePoll(): void {
    if (closed || !deps.pollSnapshot || staleHandle !== null) return;
    staleHandle = setTimeoutFn(() => {
      staleHandle = null;
      if (closed || pollInFlight || !deps.pollSnapshot) return;
      pollInFlight = true;
      deps
        .pollSnapshot()
        .then((snapshot) => {
          if (!closed) handlers.onSnapshot(snapshot);
        })
        .catch(() => {
          // Опрос недоступен — ждём родное переподключение EventSource.
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

  // Бэкенд шлёт именованные события (ServerSentEvent(event="snapshot")),
  // поэтому подписка через addEventListener: onmessage именованные кадры
  // не доставляет.
  const onSnapshotFrame = (event: Event): void => {
    if (closed) return;
    clearStaleTimer();
    let parsed: unknown;
    try {
      parsed = JSON.parse((event as MessageEvent<string>).data);
    } catch {
      return; // некорректный кадр игнорируется, поток продолжается
    }
    if (!isJobSnapshot(parsed)) return;
    handlers.onSnapshot(parsed);
    if (
      parsed.status === "succeeded" ||
      parsed.status === "cancelled" ||
      parsed.status === "failed" ||
      parsed.status === "interrupted"
    ) {
      close();
    }
  };
  source.addEventListener("snapshot", onSnapshotFrame);

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
}
