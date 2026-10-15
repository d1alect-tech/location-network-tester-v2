/** 409-исход живого режима (задача 15, зона-карта §8.9): конфликт
 * LIVE_ALREADY_RUNNING (routes_live.py:95-97) завершается баннером
 * «Запуск уже выполняется на вкладке …» с кнопкой «Перейти и остановить»,
 * а не мёртвой кнопкой Run. Два пути детекта, оба без правок воркспейса:
 * (1) статус-код ApiError — обёртка signalLiveConflicts над live-контуром
 * (запасной путь на дрейф текста), проводит AppShell в живые кнопки
 * вкладки; (2) текст-зеркало строки models_live.py — наблюдение ре-парент
 * errorHost. Кнопка останавливает поток (stop идемпотентен) и переводит
 * на вкладку-конкурента; без 409 баннера нет. */

import type { LiveApi } from "../../api/client-live";
import { ApiError } from "../../api/errors";
import { el } from "../primitives/dom";

/** Зеркало LIVE_ALREADY_RUNNING_RU из src/lnt/ui/models_live.py:50 —
 * причина отказа 409 на языке панели. Дрейф строки ловит
 * liveConflict.test.ts (квитанция зеркала). */
export const LIVE_ALREADY_RUNNING_RU = "живой режим уже запущен: сначала stop";

/** Сигнал 409 старта: обёртка контура эмитит, клетка конфликта слушает. */
export interface LiveConflictSignal {
  emit(error: ApiError): void;
  subscribe(listener: (error: ApiError) => void): () => void;
}

export function createLiveConflictSignal(): LiveConflictSignal {
  const listeners = new Set<(error: ApiError) => void>();
  return {
    emit: (error) => {
      for (const listener of [...listeners]) listener(error);
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/** Обёртка live-контура: 409 старта уходит сигналом, всё остальное —
 * прозрачное делегирование (воркспейс не меняется ни строкой). */
export function signalLiveConflicts(live: LiveApi, signal: LiveConflictSignal): LiveApi {
  return {
    state: (options) => live.state(options),
    start: async (request, options) => {
      try {
        return await live.start(request, options);
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) signal.emit(error);
        throw error;
      }
    },
    stop: (options) => live.stop(options),
    updateConfig: (config, options) => live.updateConfig(config, options),
    updateTrigger: (trigger, options) => live.updateTrigger(trigger, options),
    stopIfActive: (options) => live.stopIfActive(options),
    watchFrames: (handlers, deps) => live.watchFrames(handlers, deps),
  };
}

export interface LiveConflictOptions {
  /** Ре-парент errorHost вкладки (absolute-оверлей статус-зоны полосы). */
  errorHost: HTMLElement;
  /** Вкладка-конкурент: «Осциллограф»/«Спектроанализатор». */
  otherRoute: "scope" | "sa";
  otherTitle: string;
  /** Остановка потока (sharedLiveApi().stop) — идемпотентна. */
  stop: () => Promise<unknown>;
  /** Статус-код путь (обёртка signalLiveConflicts). */
  signal?: LiveConflictSignal;
}

export interface LiveConflictHandle {
  dispose(): void;
}

export function mountLiveConflict(options: LiveConflictOptions): LiveConflictHandle {
  let banner: HTMLElement | null = null;
  let disposed = false;

  function buildBanner(): HTMLElement {
    const reason = el("p", {
      className: "lnt-live-conflict-reason",
      text: LIVE_ALREADY_RUNNING_RU,
      attrs: { "data-readonly": "" },
    });
    const goto = el("button", {
      className: "lnt-live-conflict-goto",
      text: "Перейти и остановить",
      attrs: { type: "button" },
    });
    goto.addEventListener("click", () => {
      goto.disabled = true;
      void options
        .stop()
        .then(() => {
          window.location.hash = `#/${options.otherRoute}`;
        })
        .catch(() => {
          // Стоп не прошёл: кнопка остаётся рабочей, переход не врёт.
          goto.disabled = false;
        });
    });
    return el("section", { className: "lnt-live-conflict", attrs: { role: "alert" } }, [
      el("p", {
        className: "lnt-live-conflict-text",
        text: `Запуск уже выполняется на вкладке «${options.otherTitle}» — остановите его там.`,
      }),
      reason,
      goto,
    ]);
  }

  function showBanner(): void {
    if (disposed) return;
    if (banner?.isConnected && options.errorHost.contains(banner)) return;
    banner ??= buildBanner();
    // Баннер честно заменяет сырую ошибку: текст зеркала уже внутри.
    options.errorHost.replaceChildren(banner);
  }

  // Текст-зеркало: ошибки errorHost с дословной причиной бэкенда.
  const observer = new MutationObserver(() => {
    const text = options.errorHost.textContent ?? "";
    if (text.includes(LIVE_ALREADY_RUNNING_RU)) showBanner();
  });
  observer.observe(options.errorHost, { childList: true, subtree: true, characterData: true });

  const unsubscribe = options.signal?.subscribe((error) => {
    if (error.status !== 409) return;
    // Воркспейс печатает сырую ошибку синхронно в catch ПОСЛЕ сигнала:
    // баннер встаёт следующим макрозаданием поверх неё — и остаётся
    // единственным сообщением об исходе (текст зеркала уже внутри).
    window.setTimeout(() => showBanner(), 0);
  });

  return {
    dispose: () => {
      disposed = true;
      observer.disconnect();
      unsubscribe?.();
    },
  };
}
