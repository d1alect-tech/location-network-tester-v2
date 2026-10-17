/** ЕДИНЫЙ словарь причин Инспекции (D2, задача 3 ui-refactor-3).
 *
 * Один источник фраз отсутствия/отказа для трёх существующих диалектов:
 * showError-лента (inspectV6 onPairChange/boot), чипы w1Render (panels/host →
 * renderAbsent/renderFailures) и «н/д»-значения ленты анализа (analysisBand).
 * Диалекты потребляют словарь БЕЗ изменения пиннутого рендера.
 *
 * `PairLoadOutcome` производится существующим onPairChange try/catch в
 * inspectV6.ts и передаётся через существующие сеттеры секций — отдельного
 * модуля состояния pair-load нет (D2 concession).
 *
 * Reason-строка ошибки = canned-префикс (`ApiError.message` из RU_MESSAGES —
 * единственного источника canned-копий api/errors.ts) + серверный detail
 * ПОСЛЕ префикса, если сервер его прислал (409/422/…); без detail — только
 * префикс, никогда «undefined». */

import { ApiError } from "../../api/errors";

// ---- Фразы словаря: единственный источник, тексты пиннуты существующими спеками ----

/** Значение отсутствия в ленте анализа (пин analysisBand.test.ts — toBe). */
export const REASON_UNAVAILABLE = "н/д";

/** Чип отсутствия артефакта (пины host.test.ts / w1Chrome.test.ts). */
export const REASON_NO_ARTIFACT = "нет артефакта";

/** Ошибка без сообщения: честное «неизвестно», без выдуманной конкретики. */
export const REASON_UNKNOWN = "Неизвестная ошибка";

const BRANCH_NOT_COMPUTED = "ветка не посчитана";

/** Чип провала ветки: фраза словаря + сообщение ветки, если оно есть. */
export function branchNotComputedReason(message: string): string {
  return message === "" ? BRANCH_NOT_COMPUTED : `${BRANCH_NOT_COMPUTED}: ${message}`;
}

/** Строка провала именованной ветки (диалект renderFailures). */
export function namedBranchNotComputedReason(branch: string, message: string): string {
  return `ветка ${branch} не посчитана: ${message}`;
}

/** Чип withheld-панели: честный счётчик циклов против минимума. */
export function insufficientCyclesReason(cycles: number, minimum: number): string {
  return `недостаточно циклов (${String(cycles)} из ${String(minimum)})`;
}

// ---- PairLoadOutcome ----

/** Отказ загрузки пары: absent — данные отсутствуют (404); failed — загрузка
 * отказала. reason всегда из одного словаря. */
export type PairLoadFailure =
  | { readonly kind: "absent"; readonly reason: string }
  | { readonly kind: "failed"; readonly reason: string };

/** Исход загрузки пары: ok — данные есть; absent — данные отсутствуют (404);
 * failed — загрузка отказала. reason всегда из одного словаря. */
export type PairLoadOutcome = { readonly kind: "ok" } | PairLoadFailure;

export const PAIR_LOAD_OK: PairLoadOutcome = { kind: "ok" };

export function pairAbsent(reason: string): PairLoadFailure {
  return { kind: "absent", reason };
}

export function pairFailed(reason: string): PairLoadFailure {
  return { kind: "failed", reason };
}

/** Reason из одной схемы: canned-префикс + серверный detail после префикса;
 * для не-API ошибок — сообщение Error или REASON_UNKNOWN. */
export function reasonFromError(error: unknown): string {
  if (error instanceof ApiError) {
    const { detail } = error;
    return detail !== undefined && detail !== "" ? `${error.message} ${detail}` : error.message;
  }
  if (error instanceof Error && error.message !== "") return error.message;
  return REASON_UNKNOWN;
}

/** Классификация исхода pair-load: 404 = данные отсутствуют (absent),
 * остальное = отказ загрузки (failed); ok производится успешной ветвью. */
export function pairLoadOutcomeFrom(error: unknown): PairLoadFailure {
  const reason = reasonFromError(error);
  return error instanceof ApiError && error.status === 404
    ? pairAbsent(reason)
    : pairFailed(reason);
}
