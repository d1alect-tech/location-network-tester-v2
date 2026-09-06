/** Чистый конечный автомат хронологии задачи: дедупликация версий,
 * отмена на безопасной границе, восстановление после прерывания.
 * Никакого DOM и сети — только состояние и селекторы. */

import type { JobSnapshot, JobStage, JobStatus } from "../api/types-jobs";

export type ConnectionKind = "idle" | "live" | "reconnecting" | "stale" | "closed";

export interface TimelineState {
  /** Последний принятый снимок (максимальная версия). */
  readonly latest: JobSnapshot | null;
  /** Принятые снимки по возрастанию версии (устаревшие отброшены). */
  readonly history: JobSnapshot[];
  readonly connection: ConnectionKind;
  /** Оператор запросил отмену; подтверждение приходит снимком cancelling. */
  readonly cancelRequested: boolean;
}

export const initialTimeline: TimelineState = {
  latest: null,
  history: [],
  connection: "idle",
  cancelRequested: false,
};

const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set([
  "succeeded",
  "cancelled",
  "failed",
  "interrupted",
]);

/** Принимает снимок только если он новее последнего (дедуп out-of-order/stale). */
export function applySnapshot(state: TimelineState, snapshot: JobSnapshot): TimelineState {
  if (state.latest !== null && snapshot.version <= state.latest.version) return state;
  return {
    ...state,
    latest: snapshot,
    history: [...state.history, snapshot],
  };
}

export function setConnection(state: TimelineState, connection: ConnectionKind): TimelineState {
  if (state.connection === connection) return state;
  return { ...state, connection };
}

/** Намерение оператора: отменить после текущей сессии серии. */
export function requestCancel(state: TimelineState): TimelineState {
  if (!canCancel(state)) return state;
  return { ...state, cancelRequested: true };
}

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

/** Отмена доступна, пока задача активна и подтверждения cancelling ещё нет. */
export function canCancel(state: TimelineState): boolean {
  const status = state.latest?.status;
  return status === "queued" || status === "running";
}

/** Бэкенд подтвердил отмену: завершится после текущей сессии серии. */
export function cancelAtBoundary(state: TimelineState): boolean {
  return state.latest?.status === "cancelling";
}

/** Задача выполняется (нужна блокировка стартовых контролов). */
export function isActive(state: TimelineState): boolean {
  const status = state.latest?.status;
  return status !== undefined && !isTerminal(status);
}

/** Прерванная задача требует подсказку восстановления после перезапуска сервера. */
export function needsRecoveryPrompt(state: TimelineState): boolean {
  return state.latest?.status === "interrupted";
}

/** Повтор возможен для неуспешных терминальных исходов. */
export function canRetry(state: TimelineState): boolean {
  const status = state.latest?.status;
  return status === "failed" || status === "cancelled" || status === "interrupted";
}

/** «Серия 2 из 5» или null для одиночной записи. */
export function seriesText(state: TimelineState): string | null {
  const { series_index: index, series_total: total } = state.latest ?? {};
  if (total === null || total === undefined) return null;
  return `Серия ${index ?? "—"} из ${total}`;
}

export const STAGE_LABELS_RU: Record<JobStage, string> = {
  queued: "в очереди",
  simulating: "симуляция",
  capturing: "захват",
  analyzing: "анализ",
  comparing: "сравнение",
  selftest: "самопроверка",
  checking_device: "проверка устройства",
  backup: "резервное копирование",
  support_bundle: "сборник поддержки",
  done: "готово",
};

export const STATUS_LABELS_RU: Record<JobStatus, string> = {
  queued: "Задача в очереди",
  running: "Задача выполняется",
  cancelling: "Отмена после текущей сессии",
  succeeded: "Задача завершена",
  cancelled: "Задача отменена",
  failed: "Задача завершилась с ошибкой",
  interrupted: "Задача прервана перезапуском сервера",
};

/** Причина занятости для заблокированных стартовых контролов (не молчаливая). */
export function busyReasonRu(state: TimelineState): string | null {
  if (!isActive(state)) return null;
  if (cancelAtBoundary(state)) {
    return "Задача отменяется после текущей сессии — дождитесь завершения.";
  }
  return "Задача ещё выполняется — дождитесь завершения или отмените её.";
}
