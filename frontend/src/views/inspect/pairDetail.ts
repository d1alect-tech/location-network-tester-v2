/** B2 (ui-refactor-2, todo 13): один источник `plots.detail` на пару инспекции.
 * Секция спектр+грам, лента анализа и секция analysis-v2 читают одну и ту же
 * сессию базы; до объединения каждая тянула detail своим запросом (три fetch
 * на смену пары). Здесь — один fetch на пару, общий для всех потребителей,
 * и общий отменитель: смена пары сбрасывает кэш и гасит предыдущий запрос. */

import type { SessionDetailPayload } from "../../api/types-plots";

export type DetailLoader = (
  name: string,
  options?: { readonly signal?: AbortSignal },
) => Promise<SessionDetailPayload>;

export type PairDetailHandle = {
  /** Общий загрузчик: повторный вызов для той же сессии в рамках пары не fetch-ит. */
  readonly load: DetailLoader;
  /** Новая пара: кэш сброшен, предыдущий запрос отменён. */
  reset(): void;
  /** Teardown вида: отмена без нового поколения. */
  dispose(): void;
};

function abortError(): DOMException {
  return new DOMException("aborted", "AbortError");
}

/** Отмена потребителя рвёт его ожидание, но не общий запрос: иначе смена
 * плоскости в одной секции отменила бы detail для ленты и панелей. */
function withSignal<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (signal === undefined) return promise;
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise<T>((resolve, reject) => {
    const onAbort = (): void => reject(abortError());
    signal.addEventListener("abort", onAbort, { once: true });
    const done = (fn: () => void): void => {
      signal.removeEventListener("abort", onAbort);
      fn();
    };
    promise.then(
      (value) => done(() => resolve(value)),
      (error: unknown) => done(() => reject(error instanceof Error ? error : abortError())),
    );
  });
}

export function createPairDetail(fetchDetail: DetailLoader): PairDetailHandle {
  const cache = new Map<string, Promise<SessionDetailPayload>>();
  let controller = new AbortController();
  let disposed = false;

  function reset(): void {
    cache.clear();
    controller.abort();
    controller = new AbortController();
  }

  return {
    load(name, options) {
      if (disposed) return Promise.reject(abortError());
      const cached = cache.get(name);
      if (cached !== undefined) return withSignal(cached, options?.signal);
      const request = fetchDetail(name, { signal: controller.signal });
      cache.set(name, request);
      // Общий промис наблюдают потребители; собственный catch гасит
      // unhandled-rejection, когда поколение сброшено до их обращения.
      request.catch(() => undefined);
      return withSignal(request, options?.signal);
    },
    reset,
    dispose() {
      disposed = true;
      reset();
    },
  };
}
