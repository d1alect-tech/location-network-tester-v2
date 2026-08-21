/** Явный конечный автомат загрузки данных и мутаций.
 * Гонки: устаревший ответ не может перезаписать текущую выборку —
 * каждая загрузка получает номер поколения, плюс AbortController. */

import { ApiError, isAbortError, normalizeThrown } from "../api/errors";

export type ResourceState<T> =
  | { kind: "idle" }
  | { kind: "loading"; key: string }
  | { kind: "ready"; key: string; value: T }
  | { kind: "error"; key: string; error: ApiError };

export interface ResourceLoader<T> {
  get(): ResourceState<T>;
  subscribe(listener: (state: ResourceState<T>) => void): () => void;
  load(key: string): Promise<void>;
  retry(): Promise<void>;
}

export function createResourceLoader<T>(
  fetcher: (key: string, signal: AbortSignal) => Promise<T>,
): ResourceLoader<T> {
  let state: ResourceState<T> = { kind: "idle" };
  let generation = 0;
  let lastKey: string | null = null;
  let activeController = new AbortController();
  const listeners = new Set<(state: ResourceState<T>) => void>();

  function set(next: ResourceState<T>): void {
    state = next;
    for (const listener of listeners) listener(next);
  }

  async function load(key: string): Promise<void> {
    lastKey = key;
    const gen = ++generation;
    activeController.abort();
    const controller = new AbortController();
    activeController = controller;
    set({ kind: "loading", key });
    try {
      const value = await fetcher(key, controller.signal);
      if (gen !== generation) return; // устаревший ответ — игнорируем
      set({ kind: "ready", key, value });
    } catch (error) {
      if (gen !== generation || isAbortError(error)) return; // замещён новый запрос
      set({ kind: "error", key, error: normalizeThrown(error) });
    }
  }

  return {
    get: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    load,
    retry: async () => {
      if (lastKey !== null) await load(lastKey);
    },
  };
}

export type MutationState<T> =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "success"; value: T }
  | { kind: "failure"; error: ApiError };

export interface Mutation<I, O> {
  get(): MutationState<O>;
  subscribe(listener: (state: MutationState<O>) => void): () => void;
  run(input: I): Promise<O>;
  reset(): void;
}

/** Каждая мутация exposes pending/success/failure для блокировки контролов. */
export function createMutation<I, O>(action: (input: I) => Promise<O>): Mutation<I, O> {
  let state: MutationState<O> = { kind: "idle" };
  const listeners = new Set<(state: MutationState<O>) => void>();

  function set(next: MutationState<O>): void {
    state = next;
    for (const listener of listeners) listener(next);
  }

  return {
    get: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    run: async (input: I) => {
      set({ kind: "pending" });
      try {
        const value = await action(input);
        set({ kind: "success", value });
        return value;
      } catch (error) {
        const apiError = isAbortError(error)
          ? new ApiError("network", { code: "aborted", cause: error })
          : normalizeThrown(error);
        set({ kind: "failure", error: apiError });
        throw apiError;
      }
    },
    reset: () => {
      set({ kind: "idle" });
    },
  };
}
