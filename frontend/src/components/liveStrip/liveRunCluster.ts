/** Слитый run-кластер полосы liveStrip (задача 14, зона-карта 13): обёртка
 * двух РЕ-ПАРЕНТ кнопок пуска/останова (#lnt-scope-run/#lnt-scope-stop) —
 * пара role=switch «ЗАПУСК»/«СТОП» с глифами ▶/■ (нечветовые носители
 * состояния), бейдж «отложено к запуску» (pendingCount staged-реестра),
 * глобальный spacebar вне интерактива и текстовых полей, программный
 * restart для автосета (стоп → свободен → пуск). Состояние ПОТРЕБЛЯЕТСЯ из
 * live-источника: кластер красит пару по onState и НИКОГДА не владеет
 * run-состоянием (disabled и запросы — работа воркспейса); dispose
 * отписывается от источника и документа. */

import type { LiveStatePayload } from "../../api/types-live";
import { el } from "../primitives/dom";
import type { LiveStateSource } from "./liveStrip";

export interface LiveRunClusterOptions {
  run: HTMLButtonElement;
  stop: HTMLButtonElement;
  live: LiveStateSource;
}

export interface LiveRunClusterHandle {
  readonly root: HTMLElement;
  /** Бейдж «отложено к запуску»: виден при staged≠∅ (pendingCount > 0). */
  setPendingCount(count: number): void;
  /** Программный рестарт (автосет, задача 15): стоп → освобождение → пуск. */
  restart(): void;
  dispose(): void;
}

/** Интерактив, где Space остаётся нативной активацией самого элемента. */
const INTERACTIVE =
  "button, input, select, textarea, a[href], [contenteditable='true'], [role='option']";

export function mountLiveRunCluster(options: LiveRunClusterOptions): LiveRunClusterHandle {
  const { run, stop, live } = options;
  let running = false;
  let restartPending = false;

  for (const [button, glyph, text] of [
    [run, "▶", "ЗАПУСК"],
    [stop, "■", "СТОП"],
  ] as const) {
    button.setAttribute("role", "switch");
    button.replaceChildren(
      el("span", {
        className: "lnt-live-run-glyph",
        text: glyph,
        attrs: { "aria-hidden": "true" },
      }),
      el("span", { className: "lnt-live-run-text", text }),
    );
  }
  const badge = el("span", {
    className: "lnt-live-runbadge",
    text: "отложено к запуску",
    attrs: { hidden: "" },
  });
  const root = el("div", { className: "lnt-live-runctl", attrs: { "data-run-state": "idle" } }, [
    run,
    stop,
    badge,
  ]);

  function paint(): void {
    run.setAttribute("aria-checked", String(running));
    stop.setAttribute("aria-checked", String(!running));
    root.setAttribute("data-run-state", running ? "running" : "idle");
  }

  const stream = live.watchFrames({
    onConnection: () => undefined,
    onState: (state: LiveStatePayload) => {
      running = state.state === "running";
      paint();
      if (restartPending && state.state !== "running") {
        restartPending = false;
        run.click();
      }
    },
  });

  const onKeyDown = (event: KeyboardEvent): void => {
    if (event.key !== " " || event.repeat) return;
    const target = event.target;
    if (target instanceof HTMLElement && target.closest(INTERACTIVE) !== null) return;
    event.preventDefault();
    (running ? stop : run).click();
  };
  document.addEventListener("keydown", onKeyDown);

  paint();
  return {
    root,
    setPendingCount: (count) => {
      badge.hidden = count <= 0;
    },
    restart: () => {
      if (running) {
        restartPending = true;
        stop.click();
      } else {
        run.click();
      }
    },
    dispose: () => {
      document.removeEventListener("keydown", onKeyDown);
      stream.close();
    },
  };
}
