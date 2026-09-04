/** Вид хронологии задачи: текущая стадия, позиция серии i/N, записанные
 * сессии, отмена с подтверждением на безопасной границе, повтор,
 * подсказка восстановления после прерывания. */

import { openDialog } from "../components/primitives/dialog";
import { el } from "../components/primitives/dom";
import { announcePolite, createJobProgress } from "../components/primitives/status";
import {
  STAGE_LABELS_RU,
  STATUS_LABELS_RU,
  busyReasonRu,
  canCancel,
  canRetry,
  cancelAtBoundary,
  needsRecoveryPrompt,
  seriesText,
} from "./jobTimeline";
import type { TimelineState } from "./jobTimeline";

export interface TimelineViewDeps {
  /** POST /api/jobs/{id}/cancel через доменный клиент. */
  onCancel(jobId: string): void;
  /** Повтор последнего запроса задачи (failed/cancelled/interrupted). */
  onRetry(): void;
}

export interface TimelineViewHandle {
  root: HTMLElement;
  update(state: TimelineState): void;
}

export function createJobTimelineView(deps: TimelineViewDeps): TimelineViewHandle {
  const progress = createJobProgress();
  const statusLine = el("p", { className: "capture-job-status t-compact" });
  const stageLine = el("p", { className: "capture-job-stage t-compact" });
  const seriesLine = el("p", { className: "capture-job-series t-compact" });
  seriesLine.hidden = true;
  const connectionLine = el("p", {
    className: "capture-job-connection t-compact",
    text: "Связь с задачей прервана, ожидаем восстановление…",
    attrs: { role: "status" },
  });
  connectionLine.hidden = true;
  const writtenWrap = el("div", { className: "capture-job-written" });
  const recoveryBanner = el("div", {
    className: "capture-recovery-banner banner banner-inline banner-warn",
    attrs: { role: "alert" },
  });
  recoveryBanner.hidden = true;
  const onboarding = el("p", {
    className: "lnt-hint",
    text: "Задач пока нет. Запустите захват — здесь появятся стадия, серия и записанные сессии.",
    attrs: { role: "status", "data-timeline-onboarding": "" },
  });

  const cancelButton = el("button", {
    className: "lnt-btn btn-secondary",
    text: "Отменить после текущей сессии",
    attrs: { type: "button", disabled: "disabled" },
  }) as HTMLButtonElement;
  const retryButton = el("button", {
    className: "lnt-btn btn-quiet",
    text: "Повторить задачу",
    attrs: { type: "button", disabled: "disabled" },
  }) as HTMLButtonElement;

  let latestState: TimelineState = {
    latest: null,
    history: [],
    connection: "idle",
    cancelRequested: false,
  };

  cancelButton.addEventListener("click", () => {
    const jobId = latestState.latest?.job_id;
    if (!jobId || !canCancel(latestState)) return;
    openDialog({
      title: "Отмена задачи",
      content: el("p", {
        text: "Отмена будет выполнена на безопасной границе: после завершения текущей записи серии. Подтвердить отмену?",
      }),
      actions: [
        {
          label: "Подтвердить отмену",
          kind: "primary",
          onClick: (close) => {
            close();
            deps.onCancel(jobId);
          },
        },
      ],
    });
  });

  retryButton.addEventListener("click", () => {
    if (!canRetry(latestState)) return;
    deps.onRetry();
  });

  const root = el(
    "section",
    { className: "capture-timeline panel", attrs: { "aria-label": "Хронология задачи" } },
    [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "capture-section-title panel-title", text: "Активная задача" }),
      ]),
      onboarding,
      recoveryBanner,
      connectionLine,
      statusLine,
      stageLine,
      seriesLine,
      progress.root,
      writtenWrap,
      el("div", { className: "capture-job-actions statusbar" }, [cancelButton, retryButton]),
    ],
  );

  return {
    root,
    update: (state) => {
      const previousStatus = latestState.latest?.status;
      latestState = state;
      const snapshot = state.latest;
      if (snapshot === null) {
        root.hidden = false;
        onboarding.hidden = false;
        statusLine.textContent = "";
        stageLine.textContent = "";
        seriesLine.hidden = true;
        connectionLine.hidden = true;
        recoveryBanner.hidden = true;
        cancelButton.disabled = true;
        retryButton.disabled = true;
        return;
      }
      root.hidden = false;
      onboarding.hidden = true;

      const terminal =
        snapshot.status === "succeeded" ||
        snapshot.status === "cancelled" ||
        snapshot.status === "failed" ||
        snapshot.status === "interrupted";

      statusLine.textContent =
        STATUS_LABELS_RU[snapshot.status] +
        (snapshot.error_message ? ` ${snapshot.error_message}` : "");
      stageLine.textContent = `Стадия: ${STAGE_LABELS_RU[snapshot.stage] ?? snapshot.stage}`;

      const series = seriesText(state);
      seriesLine.hidden = series === null;
      if (series !== null && !terminal) {
        progress.setStage(series, snapshot.series_index ?? 0, snapshot.series_total ?? 1);
        seriesLine.textContent = `${series} · стадия: ${STAGE_LABELS_RU[snapshot.stage]}`;
      }

      // Связь: reconnecting/stale показывают ожидание восстановления.
      const degraded = state.connection === "reconnecting" || state.connection === "stale";
      connectionLine.hidden = !degraded || terminal;

      // Отмена: доступна до подтверждения cancelling; после — пояснение границы.
      cancelButton.disabled = !canCancel(state);
      cancelButton.setAttribute("aria-disabled", String(!canCancel(state)));
      if (cancelAtBoundary(state)) {
        cancelButton.textContent = "Отмена запланирована после текущей сессии";
      } else {
        cancelButton.textContent = "Отменить после текущей сессии";
      }
      retryButton.disabled = !canRetry(state);

      // Записанные сессии серии.
      while (writtenWrap.firstChild) writtenWrap.removeChild(writtenWrap.firstChild);
      if (snapshot.written_sessions.length > 0) {
        writtenWrap.append(
          el("p", { className: "lnt-hint", text: "Записанные сессии:" }),
          el(
            "ul",
            { className: "capture-written-list" },
            snapshot.written_sessions.map((name) =>
              el("li", { className: "capture-written-item lnt-mono cell-wrap", text: name }),
            ),
          ),
        );
      }

      // Восстановление после перезапуска сервера.
      recoveryBanner.hidden = !needsRecoveryPrompt(state);
      if (needsRecoveryPrompt(state)) {
        while (recoveryBanner.firstChild) recoveryBanner.removeChild(recoveryBanner.firstChild);
        recoveryBanner.append(
          el("p", {
            className: "banner-msg",
            text: "Задача была прервана из-за перезапуска сервера. Данные сохранены частично.",
          }),
          el("p", {
            className: "lnt-hint",
            text: "Следующее действие: повторите задачу или выберите другую операцию.",
          }),
        );
      }

      // Причина занятости объявляется, а клики блокируются осознанно (не молча).
      const busy = busyReasonRu(state);
      if (busy !== null && previousStatus !== snapshot.status) announcePolite(busy);
      if (terminal) {
        progress.done();
        announcePolite(STATUS_LABELS_RU[snapshot.status]);
      }
    },
  };
}
