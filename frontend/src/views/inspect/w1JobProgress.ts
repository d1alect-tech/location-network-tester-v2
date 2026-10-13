/** Задача 8 (D1e/R5): честный прогресс задачи анализа v2. Состояние — из
 * реальных SSE-снимков; транспорт — capture/sse.ts (кросс-видовой импорт
 * views/inspect → views/capture разрешён планом R5), словарь стадий и
 * статусов — capture/jobTimeline, дедупликация версий — его applySnapshot.
 *
 * Числовая доля НИКОГДА не выдумывается: стадия без серийных данных —
 * indeterminate, не сфабрикованный 0.5 («unavailable, never fabricated»).
 *
 * Ожидание терминала: watchJobEvents даёт живые кадры, а исход подтверждает
 * собственный опрос задачи (прецедент pollDone в extendedRun.ts: задачу
 * ждут, а не только показывают). Подряд неудачные опросы честно прерывают
 * ожидание последней ошибкой — контролы не виснут на мёртвом соединении;
 * fallback-опрос sse.ts здесь не годится: он гасится каждым живым
 * переподключением и не умеет «сдаться». */

import type { JobSnapshot, JobStage, JobStatus } from "../../api/types-jobs";
import {
  STAGE_LABELS_RU,
  STATUS_LABELS_RU,
  applySnapshot,
  initialTimeline,
  isTerminal,
} from "../../capture/jobTimeline";
import type { TimelineState } from "../../capture/jobTimeline";
import { watchJobEvents } from "../../capture/sse";
import type { WatchHandle } from "../../capture/sse";

/** Отрисовка прогресса из одного снимка: indeterminate | серия i/N | терминал. */
export type JobProgressView =
  | { readonly kind: "indeterminate"; readonly label: string }
  | {
      readonly kind: "series";
      readonly label: string;
      readonly index: number;
      readonly total: number;
    }
  | { readonly kind: "terminal"; readonly label: string; readonly succeeded: boolean };

/** Стадия из словаря capture: незнакомое значение показывается как есть. */
export function stageLabelOf(stage: JobStage): string {
  return STAGE_LABELS_RU[stage] ?? stage;
}

/** Строка исхода: статус словаря + серверное сообщение, если оно есть. */
export function jobStatusLabel(status: JobStatus, message: string | null): string {
  return message === null || message === ""
    ? STATUS_LABELS_RU[status]
    : `${STATUS_LABELS_RU[status]} ${message}`;
}

export function jobProgressView(snapshot: JobSnapshot): JobProgressView {
  if (isTerminal(snapshot.status)) {
    return {
      kind: "terminal",
      label: jobStatusLabel(snapshot.status, snapshot.error_message ?? null),
      succeeded: snapshot.status === "succeeded",
    };
  }
  const stage = stageLabelOf(snapshot.stage);
  const { series_index: index, series_total: total } = snapshot;
  if (index !== null && total !== null && total > 0) {
    return { kind: "series", label: stage, index: Math.min(index, total), total };
  }
  return { kind: "indeterminate", label: `Стадия: ${stage}` };
}

export interface W1JobWatchOptions {
  /** Фальшивый конструктор для юнит-тестов (jsdom без EventSource). */
  readonly eventSourceCtor?: typeof EventSource;
  /** Интервал подтверждающего опроса задачи, мс (прецедент extendedRun). */
  readonly pollIntervalMs?: number;
  /** Сколько подряд неудачных опросов означают недоступность задачи. */
  readonly giveUpAfterPolls?: number;
}

export interface JobWatchHandle {
  /** Терминальный снимок; reject — задача недоступна (последняя ошибка
   * опроса) либо ожидание закрыто teardown'ом (AbortError). */
  readonly result: Promise<JobSnapshot>;
  close(): void;
}

const DEFAULT_POLL_INTERVAL_MS = 1500;
const DEFAULT_GIVE_UP_AFTER = 3;

/** Ожидание терминального снимка задачи: живые кадры SSE идут в onSnapshot
 * (отрисовка), терминал резолвит ожидание, серию неудачных опросов честно
 * прерывает последней ошибкой. Стартовый снимок участвует в дедупе версий. */
export function watchJobTerminal(
  started: JobSnapshot,
  onSnapshot: (snapshot: JobSnapshot) => void,
  pollSnapshot: () => Promise<JobSnapshot>,
  options: W1JobWatchOptions = {},
): JobWatchHandle {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const giveUpAfter = options.giveUpAfterPolls ?? DEFAULT_GIVE_UP_AFTER;
  let state: TimelineState = applySnapshot(initialTimeline, started);
  let pollFailures = 0;
  let settled = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let watch: WatchHandle | null = null;
  let lastPollError: unknown = null;
  let resolveResult: ((snapshot: JobSnapshot) => void) | undefined;
  let rejectResult: ((error: unknown) => void) | undefined;
  const result = new Promise<JobSnapshot>((resolve, reject) => {
    resolveResult = resolve;
    rejectResult = reject;
  });

  function settle(finish: () => void): void {
    if (settled) return;
    settled = true;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    watch?.close();
    finish();
  }

  function deliver(snapshot: JobSnapshot): void {
    const next = applySnapshot(state, snapshot);
    if (next === state) return; // устаревший или дублирующий кадр
    state = next;
    onSnapshot(snapshot);
    if (isTerminal(snapshot.status)) {
      const final = snapshot;
      settle(() => resolveResult?.(final));
    }
  }

  function schedulePoll(): void {
    if (settled) return;
    timer = setTimeout(() => {
      timer = null;
      pollSnapshot()
        .then((snapshot) => {
          pollFailures = 0;
          deliver(snapshot);
        })
        .catch((error: unknown) => {
          pollFailures += 1;
          lastPollError = error;
        })
        .finally(() => {
          if (pollFailures >= giveUpAfter) {
            settle(() => rejectResult?.(lastPollError));
            return;
          }
          schedulePoll();
        });
    }, pollIntervalMs);
  }

  watch = watchJobEvents(
    started.job_id,
    { onSnapshot: deliver, onConnection: () => undefined },
    { eventSourceCtor: options.eventSourceCtor },
  );
  schedulePoll();

  return {
    result,
    close: () => {
      // Teardown вида: ожидание прерывается, задача продолжает жить на сервере.
      settle(() => rejectResult?.(new DOMException("aborted", "AbortError")));
    },
  };
}
