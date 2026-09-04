/** Поллинг спектра live-панели: только существующие GET spectrum через plots-api.
 * Пока job активен — спектр последней written_session каждые LIVE_POLL_MS;
 * в idle — одна post-hoc догрузка последней завершённой сессии;
 * без данных — пустое состояние, не ошибка. */

import type { JobSnapshot } from "../api/types-jobs";
import type { SpectrumPayload } from "../api/types-plots";
import { initialTimeline, isActive } from "./jobTimeline";
import { LIVE_FLOOR_DB } from "./spectrogramLiveRenderer";

/** Пауза между опросами спектра активной задачи, мс. */
export const LIVE_POLL_MS = 1500;
/** Лёгкий срез спектра для опроса (полный не нужен полотну 256 бинов). */
export const LIVE_MAX_POINTS = 2000;

export type LiveKind = "live" | "fallback";

export interface SpectrumFetch {
  spectrum(
    name: string,
    maxPoints?: number,
    options?: { signal?: AbortSignal },
  ): Promise<SpectrumPayload>;
}

export interface LivePollerHooks {
  onColumn(frequencyHz: readonly number[], psdDb: readonly number[]): void;
  onSession(name: string, kind: LiveKind): void;
  onEmpty(): void;
}

export interface LivePoller {
  notifySnapshot(snapshot: JobSnapshot | null): void;
  stop(): void;
  dispose(): void;
}

function lastWritten(snapshot: JobSnapshot | null): string | null {
  const written = snapshot?.written_sessions;
  if (written === undefined || written.length === 0) return null;
  return written[written.length - 1] as string;
}

/** Активная задача с записанными сессиями — поллить последнюю. */
export function pickLiveSessionName(snapshot: JobSnapshot | null): string | null {
  if (snapshot === null) return null;
  if (!isActive({ ...initialTimeline, latest: snapshot })) return null;
  return lastWritten(snapshot);
}

/** Idle с завершённой сессией — показать последнюю post-hoc. */
export function pickFallbackSessionName(snapshot: JobSnapshot | null): string | null {
  if (snapshot === null) return null;
  if (isActive({ ...initialTimeline, latest: snapshot })) return null;
  if (snapshot.status !== "succeeded") return null;
  return lastWritten(snapshot);
}

/** Линейная PSD в дБ; неположительная и нечисловая — пол. */
export function toDbColumn(psd: readonly number[]): number[] {
  return psd.map((value) =>
    typeof value === "number" && Number.isFinite(value) && value > 0
      ? 10 * Math.log10(value)
      : LIVE_FLOOR_DB,
  );
}

export function createLivePoller(fetch: SpectrumFetch, hooks: LivePollerHooks): LivePoller {
  let timer: ReturnType<typeof setInterval> | null = null;
  let pollingSession: string | null = null;
  let fallbackDoneFor: string | null = null;
  let disposed = false;

  async function loadSession(name: string, kind: LiveKind): Promise<void> {
    let payload: SpectrumPayload;
    try {
      payload = await fetch.spectrum(name, LIVE_MAX_POINTS);
    } catch {
      return; // Нет данных — пустое состояние хранит панель, не ошибка.
    }
    if (disposed) return;
    if (payload.frequency_hz.length < 2) return;
    hooks.onColumn(payload.frequency_hz, toDbColumn(payload.psd_v2_per_hz));
    hooks.onSession(name, kind);
  }

  function stopTimer(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
    pollingSession = null;
  }

  return {
    notifySnapshot(snapshot) {
      if (disposed) return;
      const live = pickLiveSessionName(snapshot);
      if (live !== null) {
        fallbackDoneFor = null;
        if (live !== pollingSession) {
          stopTimer();
          pollingSession = live;
          timer = setInterval(() => {
            const current = pollingSession;
            if (current !== null) void loadSession(current, "live");
          }, LIVE_POLL_MS);
        }
        return;
      }
      stopTimer();
      const fallback = pickFallbackSessionName(snapshot);
      if (fallback === null) {
        fallbackDoneFor = null;
        hooks.onEmpty();
        return;
      }
      if (fallback !== fallbackDoneFor) {
        fallbackDoneFor = fallback;
        void loadSession(fallback, "fallback");
      }
    },
    stop() {
      stopTimer();
    },
    dispose() {
      disposed = true;
      stopTimer();
    },
  };
}
