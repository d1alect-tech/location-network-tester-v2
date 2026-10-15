/** Задача 14 RED: слитый run-кластер — обёртка двух ре-парент-кнопок
 * (#lnt-scope-run/#lnt-scope-stop): пара role=switch «ЗАПУСК»/«СТОП» с
 * глифами ▶/■ (нечветовые носители), состояние ПОТРЕБЛЯЕТСЯ из live-источника
 * (кластер не владеет run-состоянием, кнопки не disable-ит — это работа
 * воркспейса), бейдж «отложено к запуску», глобальный spacebar вне
 * интерактива, dispose отписывается (подписка мертва). */

import { afterEach, describe, expect, it } from "vitest";
import type { LiveStatePayload, LiveWatchHandle, LiveWatchHandlers } from "../../api/types-live";
import { el } from "../primitives/dom";
import { mountLiveRunCluster } from "./liveRunCluster";
import type { LiveStateSource } from "./liveStrip";

const RUNNING: LiveStatePayload = {
  state: "running",
  mode: "sim",
  busy_reason: null,
  trigger: null,
};
const IDLE: LiveStatePayload = { state: "idle", mode: "sim", busy_reason: null, trigger: null };

function mountCluster(): {
  cluster: ReturnType<typeof mountLiveRunCluster>;
  run: HTMLButtonElement;
  stop: HTMLButtonElement;
  emit: (state: LiveStatePayload) => void;
  closed: { count: number };
  runClicks: { count: number };
  stopClicks: { count: number };
} {
  const run = el("button", { text: "Запустить", attrs: { type: "button", id: "lnt-scope-run" } });
  const stop = el("button", {
    text: "Остановить",
    attrs: { type: "button", id: "lnt-scope-stop" },
  });
  stop.disabled = true;
  document.body.append(run, stop);
  const watchers: LiveWatchHandlers[] = [];
  const closed = { count: 0 };
  // Фейк моделирует настоящий EventSource: после close() доставка мертва.
  const stream = { closed: false };
  const source: LiveStateSource = {
    watchFrames: (handlers: LiveWatchHandlers): LiveWatchHandle => {
      watchers.push(handlers);
      return {
        close: () => {
          stream.closed = true;
          closed.count += 1;
        },
      };
    },
  };
  const emit = (state: LiveStatePayload): void => {
    if (stream.closed) return;
    for (const watcher of watchers) watcher.onState?.(state);
  };
  const runClicks = { count: 0 };
  const stopClicks = { count: 0 };
  run.addEventListener("click", () => {
    runClicks.count += 1;
  });
  stop.addEventListener("click", () => {
    stopClicks.count += 1;
  });
  const cluster = mountLiveRunCluster({ run, stop, live: source });
  // Тесты дергают доставку через эмиттер: доставка уважает close().
  return { cluster, run, stop, emit, closed, runClicks, stopClicks };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("mountLiveRunCluster", () => {
  it("сливает пару в кластер: текст+глиф ЗАПУСК/СТОП, role=switch, начальное состояние", () => {
    const { cluster, run, stop } = mountCluster();
    expect(run.textContent).toContain("ЗАПУСК");
    expect(run.textContent).toContain("▶");
    expect(stop.textContent).toContain("СТОП");
    expect(stop.textContent).toContain("■");
    expect(run.getAttribute("role")).toBe("switch");
    expect(stop.getAttribute("role")).toBe("switch");
    // Начало: захвата нет — «СТОП»-переключатель в положении «выключено»... пары:
    expect(stop.getAttribute("aria-checked")).toBe("true");
    expect(run.getAttribute("aria-checked")).toBe("false");
    expect(cluster.root.getAttribute("data-run-state")).toBe("idle");
  });

  it("run-контрол отражает live-источник: running → пара «ЗАПУСК» нажата, «СТОП» отпущена", () => {
    const { emit, run, stop } = mountCluster();
    emit(RUNNING);
    expect(run.getAttribute("aria-checked")).toBe("true");
    expect(stop.getAttribute("aria-checked")).toBe("false");
    expect(run.closest("[data-run-state]")?.getAttribute("data-run-state")).toBe("running");
    emit(IDLE);
    expect(run.getAttribute("aria-checked")).toBe("false");
    // Кластер НЕ владеет доступностью кнопок — disabled остаётся за воркспейсом.
    expect(stop.disabled).toBe(true);
  });

  it("бейдж «отложено к запуску» появляется при staged≠∅ и гаснет при 0", () => {
    const { cluster } = mountCluster();
    const badge = cluster.root.querySelector<HTMLElement>(".lnt-live-runbadge");
    expect(badge?.hidden).toBe(true);
    cluster.setPendingCount(2);
    expect(badge?.hidden).toBe(false);
    expect(badge?.textContent).toContain("отложено к запуску");
    cluster.setPendingCount(0);
    expect(badge?.hidden).toBe(true);
  });

  it("spacebar вне интерактива жмёт доступную кнопку пары; на кнопке — не перехватывается", () => {
    const { run, stop, emit, runClicks, stopClicks } = mountCluster();
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }),
    );
    expect(runClicks.count).toBe(1);
    emit(RUNNING);
    // Воркспейс владеет доступностью: на ходу «СТОП» доступна (кластер лишь
    // красит пару; jsdom не активирует disabled-кнопки — как настоящий браузер).
    stop.disabled = false;
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }),
    );
    expect(stopClicks.count).toBe(1);
    expect(runClicks.count).toBe(1);
    // Фокус на кнопке: Space остаётся нативной активацией, кластер не вмешивается.
    const before = runClicks.count;
    run.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }));
    expect(runClicks.count).toBe(before);
  });

  it("dispose отписывается: подписка мертва, слушатели сняты", () => {
    const { cluster, emit, closed, run, runClicks } = mountCluster();
    cluster.dispose();
    expect(closed.count).toBe(1);
    // Подписка мертва: состояние после dispose не красит кластер.
    emit(RUNNING);
    expect(run.getAttribute("aria-checked")).toBe("false");
    // Spacebar больше не перехватывается документом.
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }),
    );
    expect(runClicks.count).toBe(0);
  });
});
