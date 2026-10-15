/** Задача 15 RED: 409-клетка — конфликт живого захвата (LIVE_ALREADY_RUNNING,
 * routes_live.py:95-97) завершается баннером «Запуск уже выполняется на
 * вкладке …» с кнопкой «Перейти и остановить», а не мёртвой кнопкой Run.
 * Два пути детекта: статус-код ApiError (обёртка signalLiveConflicts —
 * запасной путь зона-карты §8.9) и текст-зеркало строки models_live.py
 * (наблюдение errorHost — первичный путь); без 409 баннера нет. Кнопка
 * останавливает поток через live.stop() и переводит на вкладку-конкурента. */

import { afterEach, describe, expect, it, vi } from "vitest";
import type { LiveApi } from "../../api/client-live";
import { ApiError } from "../../api/errors";
import { DEFAULT_LIVE_START_REQUEST, type LiveStatePayload } from "../../api/types-live";
import {
  LIVE_ALREADY_RUNNING_RU,
  createLiveConflictSignal,
  mountLiveConflict,
  signalLiveConflicts,
} from "./liveConflict";

/** Дословная строка бэкенда (models_live.py:50) — независимо от константы
 * модуля: тест-квитанция зеркала (дрейф текста обязан валить тест). */
const BACKEND_TEXT = "живой режим уже запущен: сначала stop";

const CONFLICT_409 = () => new ApiError("conflict", { status: 409 });

function mountBanner(options: { signal?: ReturnType<typeof createLiveConflictSignal> } = {}) {
  const errorHost = document.createElement("div");
  errorHost.className = "lnt-scope-error-host";
  document.body.append(errorHost);
  const stop = vi.fn(() => Promise.resolve());
  const signal = options.signal ?? createLiveConflictSignal();
  const handle = mountLiveConflict({
    errorHost,
    otherRoute: "sa",
    otherTitle: "Спектроанализатор",
    stop,
    signal,
  });
  return { errorHost, stop, signal, dispose: handle.dispose };
}

function plainError(host: HTMLElement, text: string): void {
  host.replaceChildren();
  const block = document.createElement("div");
  block.textContent = text;
  host.append(block);
}

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

afterEach(() => {
  document.body.replaceChildren();
  window.location.hash = "";
});

describe("liveConflict: 409-исход запуска", () => {
  it("зеркало текста == дословной строке бэкенда models_live.py", () => {
    expect(LIVE_ALREADY_RUNNING_RU).toBe(BACKEND_TEXT);
  });

  it("409 по статус-коду: баннер с текстом зеркала и кнопкой перехода", async () => {
    const { errorHost, signal } = mountBanner();
    signal.emit(CONFLICT_409());
    await settle();

    const banner = errorHost.querySelector<HTMLElement>(".lnt-live-conflict");
    expect(banner).not.toBeNull();
    expect(banner?.getAttribute("role")).toBe("alert");
    expect(banner?.textContent).toContain(
      "Запуск уже выполняется на вкладке «Спектроанализатор» — остановите его там",
    );
    expect(banner?.querySelector(".lnt-live-conflict-reason")?.textContent).toBe(BACKEND_TEXT);
    expect(banner?.querySelector("button")?.textContent).toBe("Перейти и остановить");
  });

  it("зеркало текста: ошибка с дословной строкой бэкенда тоже поднимает баннер", async () => {
    const { errorHost } = mountBanner();
    plainError(errorHost, `Не удалось запустить живой режим: ${BACKEND_TEXT}.`);
    await settle();

    expect(errorHost.querySelector(".lnt-live-conflict")).not.toBeNull();
  });

  it("без 409 баннера нет: обычная ошибка и не-409 сигнал молчат", async () => {
    const { errorHost, signal } = mountBanner();
    plainError(errorHost, "Не удалось запустить живой режим: Сервер вернул ошибку.");
    await settle();
    signal.emit(new ApiError("http", { status: 500 }));
    await settle();

    expect(errorHost.querySelector(".lnt-live-conflict")).toBeNull();
    expect(errorHost.textContent).toContain("Сервер вернул ошибку");
  });

  it("кнопка «Перейти и остановить»: стоп потока и переход на вкладку-конкурента", async () => {
    const { errorHost, signal, stop } = mountBanner();
    signal.emit(CONFLICT_409());
    await settle();
    const goto = errorHost.querySelector<HTMLButtonElement>(".lnt-live-conflict button");
    if (goto === null) throw new Error("нет кнопки перехода");
    goto.click();
    await settle();

    expect(stop).toHaveBeenCalledTimes(1);
    expect(window.location.hash).toBe("#/sa");
  });

  it("не-409 ошибка после баннера заменяет его (баннер только у 409)", async () => {
    const { errorHost, signal } = mountBanner();
    signal.emit(CONFLICT_409());
    await settle();
    expect(errorHost.querySelector(".lnt-live-conflict")).not.toBeNull();

    plainError(errorHost, "Не удалось остановить живой режим: Нет связи с сервером.");
    await settle();
    expect(errorHost.querySelector(".lnt-live-conflict")).toBeNull();
    expect(errorHost.textContent).toContain("Нет связи с сервером");
  });

  it("dispose: сигнал и наблюдатель errorHost мертвы", async () => {
    const { errorHost, signal, dispose } = mountBanner();
    dispose();
    signal.emit(CONFLICT_409());
    await settle();
    plainError(errorHost, `Не удалось запустить живой режим: ${BACKEND_TEXT}.`);
    await settle();

    expect(errorHost.querySelector(".lnt-live-conflict")).toBeNull();
  });
});

describe("signalLiveConflicts: обёртка live-контура (запасной путь)", () => {
  const IDLE = { state: "idle", mode: "sim", busy_reason: null, trigger: null } as const;

  function fakeLive(startImpl: () => Promise<LiveStatePayload>): LiveApi {
    const stream = { close: () => undefined };
    return {
      state: () => Promise.resolve(IDLE),
      start: () => startImpl(),
      stop: () => Promise.resolve(IDLE),
      updateConfig: () => Promise.resolve(IDLE),
      updateTrigger: () => Promise.resolve(IDLE),
      stopIfActive: () => Promise.resolve(),
      watchFrames: () => stream,
    };
  }

  it("409 старта эмитится сигналом; успех и не-409 — молчат", async () => {
    const signal = createLiveConflictSignal();
    const seen: number[] = [];
    signal.subscribe((error) => seen.push(error.status ?? 0));

    const ok = signalLiveConflicts(
      fakeLive(() => Promise.resolve(IDLE)),
      signal,
    );
    await ok.start(DEFAULT_LIVE_START_REQUEST).then(
      () => undefined,
      () => undefined,
    );

    const conflict = signalLiveConflicts(
      fakeLive(() => Promise.reject(CONFLICT_409())),
      signal,
    );
    await conflict.start(DEFAULT_LIVE_START_REQUEST).then(
      () => undefined,
      () => undefined,
    );

    const network = signalLiveConflicts(
      fakeLive(() => Promise.reject(new ApiError("network"))),
      signal,
    );
    await network.start(DEFAULT_LIVE_START_REQUEST).then(
      () => undefined,
      () => undefined,
    );

    expect(seen).toEqual([409]);
  });

  it("обёртка делегирует остальные методы live-контура", () => {
    const calls: string[] = [];
    const base = fakeLive(() => Promise.resolve(IDLE));
    const spyLive: LiveApi = {
      ...base,
      stop: () => {
        calls.push("stop");
        return Promise.resolve(IDLE);
      },
      watchFrames: () => {
        calls.push("watchFrames");
        return { close: () => undefined };
      },
    };
    const wrapped = signalLiveConflicts(spyLive, createLiveConflictSignal());
    void wrapped.stop();
    wrapped.watchFrames({
      onState: () => undefined,
      onConnection: () => undefined,
    });
    expect(calls).toEqual(["stop", "watchFrames"]);
  });
});
