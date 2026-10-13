/** Рельса задачи анализа v2 (задача 8, D1e/R5): трек createJobProgress
 * (role=progressbar, aria + текст стадии из словаря) с каноническим
 * scaleX-заполнением — тем самым баром w1Chrome.css (transform 120ms
 * ease-out, prefers-reduced-motion), теперь с реальной долей из снимков.
 * Доля — только из серийных данных; без них — честный indeterminate
 * (пустой трек, aria-busy), доля никогда не выдумывается. Провалы веток —
 * чипы renderFailures (словарь задач 3), исход — строка статуса. Здесь же
 * ожидание терминала: рельса красит каждый SSE-кадр и ждёт исход
 * (watchJobTerminal поверх capture/sse.ts); teardown закрывает ожидание. */

import type { JobSnapshot } from "../../api/types-jobs";
import { isTerminal } from "../../capture/jobTimeline";
import { el } from "../../components/primitives/dom";
import { announcePolite, createJobProgress } from "../../components/primitives/status";
import { jobProgressView, jobStatusLabel, watchJobTerminal } from "./w1JobProgress";
import type { JobWatchHandle, W1JobWatchOptions } from "./w1JobProgress";
import { parseFailures } from "./w1Parse";
import { renderFailures } from "./w1Render";

export interface W1JobRailHandle {
  /** Рельса прогресса задачи; скрыта до первого запуска задачи. */
  readonly root: HTMLElement;
  show(): void;
  /** Один снимок — одно честное состояние прогресса (включая терминал). */
  paint(snapshot: JobSnapshot): void;
  /** Задача недоступна/ожидание прервано: причина из словаря задач 3. */
  paintFailure(reason: string): void;
  /** Ждёт терминальный снимок, крася каждый кадр; reject — недоступность. */
  awaitTerminal(
    started: JobSnapshot,
    poll: () => Promise<JobSnapshot>,
    options?: W1JobWatchOptions,
  ): Promise<JobSnapshot>;
  /** Teardown вида: ожидание прерывается, задача живёт на сервере. */
  close(): void;
}

export function createW1JobRail(): W1JobRailHandle {
  const progress = createJobProgress();
  // Заполнение вложено в трек createJobProgress: класс .lnt-progress-bar —
  // публичный стиль-контракт примитива, бар w1 — его заполнение (aria-hidden:
  // роль progressbar несёт трек).
  const fill = el("div", { className: "lnt-w1-job-bar", attrs: { "aria-hidden": "true" } });
  progress.root.querySelector(".lnt-progress-bar")?.append(fill);
  const status = el("p", { className: "lnt-w1-job-status", attrs: { role: "status" } });
  status.hidden = true;
  const failuresHost = el("ul", { className: "lnt-w1-failures" });
  const root = el("div", { className: "lnt-w1-job-rail" }, [progress.root, status, failuresHost]);
  root.hidden = true;
  let activeWatch: JobWatchHandle | null = null;

  function paintFill(fraction: number): void {
    fill.style.transform = `scaleX(${String(fraction)})`;
  }

  function paint(snapshot: JobSnapshot): void {
    const view = jobProgressView(snapshot);
    if (view.kind === "indeterminate") {
      progress.setIndeterminate(view.label);
      paintFill(0);
      return;
    }
    if (view.kind === "series") {
      progress.setStage(view.label, view.index, view.total);
      paintFill(view.index / view.total);
      return;
    }
    progress.done();
    status.textContent = view.label;
    status.hidden = false;
    renderFailures(failuresHost, parseFailures(snapshot.result));
    // Неуспешный терминал — не «нулевой прогресс»: доля честно обнуляется,
    // историю провала несут строка статуса и чипы веток.
    paintFill(view.succeeded ? 1 : 0);
    announcePolite(view.label);
  }

  return {
    root,
    show() {
      root.hidden = false;
    },
    paint,
    paintFailure(reason) {
      progress.done();
      status.textContent = jobStatusLabel("failed", reason);
      status.hidden = false;
      paintFill(0);
      // «Готово» из done() перекрывается исходом — как в capture-хронологии.
      announcePolite(status.textContent);
    },
    awaitTerminal(started, poll, options) {
      paint(started);
      if (isTerminal(started.status)) return Promise.resolve(started);
      const watch = watchJobTerminal(started, paint, poll, options);
      activeWatch = watch;
      return watch.result.finally(() => {
        activeWatch = null;
      });
    },
    close() {
      activeWatch?.close();
      activeWatch = null;
    },
  };
}
