/** Представление раздела «Захват»: mode-first форма, предпросмотр профиля,
 * диагностика устройства с preflight, хронология задачи через SSE.
 * Мутации идут через доменный клиент (nonce); занятость блокирует запуск
 * осознанно с объявлением причины. */

import type { LntApiClient } from "../api/client";
import { createDeviceApi } from "../api/client-device";
import { ApiError } from "../api/errors";
import type { JobRequest, JobSnapshot } from "../api/types-jobs";
import { el } from "../components/primitives/dom";
import { announcePolite } from "../components/primitives/status";
import { createDevicePanel } from "./devicePanel";
import type { DevicePanelHandle } from "./devicePanel";
import {
  applySnapshot,
  busyReasonRu,
  initialTimeline,
  isActive,
  needsRecoveryPrompt,
} from "./jobTimeline";
import type { TimelineState } from "./jobTimeline";
import { createJobTimelineView } from "./jobTimelineView";
import type { TimelineViewHandle } from "./jobTimelineView";
import { createModeForm } from "./modeForm";
import type { ModeFormHandle } from "./modeForm";
import { buildJobRequest, validateCaptureForm } from "./modes";
import { renderProfilePreview } from "./profilePreview";
import { watchJobEvents } from "./sse";
import type { WatchHandle } from "./sse";

export interface CaptureViewHandle {
  root: HTMLElement;
  /** Закрывает SSE и обрывает незавершённые запросы (уход с маршрута). */
  dispose(): void;
}

export function createCaptureView(client: LntApiClient): CaptureViewHandle {
  const device = createDeviceApi(client);
  const form: ModeFormHandle = createModeForm();
  const devicePanel: DevicePanelHandle = createDevicePanel();
  const timeline: TimelineViewHandle = createJobTimelineView({
    onCancel: (jobId) => void cancelJob(jobId),
    onRetry: () => void startJob(lastRequest),
  });

  let stream: WatchHandle | null = null;
  let timelineState: TimelineState = initialTimeline;
  let lastRequest: JobRequest | null = null;
  let disposed = false;
  let bootstrapPromise: Promise<void> | null = null;

  const alertLine = el("p", {
    className: "capture-alert",
    attrs: { role: "alert" },
  });
  alertLine.hidden = true;

  const startButton = el("button", {
    className: "lnt-btn lnt-btn-primary",
    text: "Запустить запись",
    attrs: { type: "button" },
  }) as HTMLButtonElement;
  const deviceRefreshButton = el("button", {
    className: "lnt-btn",
    text: "Проверить устройство",
    attrs: { type: "button" },
  }) as HTMLButtonElement;

  const showAlert = (message: string): void => {
    alertLine.textContent = message;
    alertLine.hidden = false;
    announcePolite(message);
  };
  const hideAlert = (): void => {
    alertLine.hidden = true;
  };

  const refreshPreview = (): void => {
    hideAlert();
    renderProfilePreview(previewContainer, form.getMode(), form.values(), form.getSource());
  };

  const applySnapshotToTimeline = (snapshot: JobSnapshot): void => {
    timelineState = applySnapshot(timelineState, snapshot);
    timeline.update(timelineState);
  };

  function attachStream(snapshot: JobSnapshot): void {
    stream?.close();
    stream = watchJobEvents(
      snapshot.job_id,
      {
        onSnapshot: applySnapshotToTimeline,
        onConnection: (kind) => {
          timelineState = { ...timelineState, connection: kind };
          timeline.update(timelineState);
        },
      },
      { pollSnapshot: () => client.jobs.get(snapshot.job_id) },
    );
  }

  async function ensureBootstrap(): Promise<boolean> {
    bootstrapPromise ??= client
      .bootstrap()
      .then(() => undefined)
      .catch(() => undefined);
    await bootstrapPromise;
    return client.currentNonce !== null;
  }

  async function checkDeviceAndPreflight(request: JobRequest): Promise<boolean> {
    try {
      const state = await device.state();
      devicePanel.renderState(state);
      // Preflight выполняется всегда: блокировки должны быть reason-coded
      // даже когда устройство уже не готово (диагностика + отчёт вместе).
      const report = await device.preflight(request as Parameters<typeof device.preflight>[0]);
      devicePanel.renderPreflight(report);
      if (state.state !== "ready") {
        showAlert(
          "Запуск невозможен: устройство не готово. Выполните указанное диагностикой действие.",
        );
        return false;
      }
      if (!report.ready) {
        showAlert(
          "Запуск невозможен: preflight нашёл блокирующие замечания — см. панель устройства.",
        );
        return false;
      }
      return true;
    } catch (error) {
      showApiError(error);
      return false;
    }
  }

  function showApiError(error: unknown): void {
    if (disposed) return;
    if (error instanceof ApiError && error.kind === "conflict") {
      showAlert("Сервер сообщил конфликт: уже выполняется другая задача (HTTP 409).");
      return;
    }
    showAlert(
      error instanceof Error ? `Операция не выполнена: ${error.message}` : "Операция не выполнена.",
    );
  }

  async function startJob(request: JobRequest | null): Promise<void> {
    if (disposed) return;
    hideAlert();
    if (!(await ensureBootstrap())) {
      showAlert("Нет связи с сервером: панель не инициализирована. Повторите попытку.");
      return;
    }
    if (isActive(timelineState)) {
      // Осознанная блокировка с объявленной причиной — никогда не молчаливая.
      showAlert(busyReasonRu(timelineState) ?? "Задача ещё выполняется.");
      return;
    }
    if (request === null) return;

    const source = form.getSource();
    if (source === "device" && !(await checkDeviceAndPreflight(request))) return;

    startButton.disabled = true;
    try {
      const snapshot = await client.jobs.start(request);
      lastRequest = request;
      timelineState = initialTimeline;
      applySnapshotToTimeline(snapshot);
      attachStream(snapshot);
    } catch (error) {
      showApiError(error);
    } finally {
      startButton.disabled = false;
    }
  }

  async function cancelJob(jobId: string): Promise<void> {
    hideAlert();
    try {
      const snapshot = await client.jobs.cancel(jobId);
      applySnapshotToTimeline(snapshot);
    } catch (error) {
      showApiError(error);
    }
  }

  async function recoverActiveJobOnMount(): Promise<void> {
    if (!(await ensureBootstrap())) return;
    try {
      const page = await client.jobs.list(1, 0);
      const latest = page.items[0];
      if (
        latest === undefined ||
        (!needsRecoveryPrompt({ ...initialTimeline, latest }) && latest.status === "succeeded")
      ) {
        return;
      }
      timelineState = applySnapshot(initialTimeline, latest);
      timeline.update(timelineState);
      const status = latest.status;
      if (status === "queued" || status === "running" || status === "cancelling") {
        attachStream(latest);
      }
    } catch {
      // Восстановление необязательно: без истории стартовая валидна.
    }
  }

  startButton.addEventListener("click", () => {
    const { valid, errors } = validateCaptureForm(form.values());
    if (valid === null) {
      form.setErrors(errors);
      announcePolite("Форма содержит ошибки: исправьте выделенные поля.");
      return;
    }
    form.clearErrors();
    void startJob(buildJobRequest(form.getMode(), valid, form.getSource()));
  });
  deviceRefreshButton.addEventListener("click", () => {
    void ensureBootstrap().then(async () => {
      try {
        devicePanel.renderState(await device.state());
      } catch (error) {
        showApiError(error);
      }
    });
  });
  form.onChange(refreshPreview);

  const previewContainer = el("aside", {
    className: "capture-preview",
    attrs: { "aria-label": "Профиль записи" },
  });
  const root = el("section", { className: "capture-view" }, [
    el("h2", { className: "view-title", text: "Захват" }),
    el("div", { className: "capture-layout" }, [
      el("div", { className: "capture-form-column" }, [
        form.root,
        alertLine,
        el("div", { className: "capture-start-row" }, [startButton, deviceRefreshButton]),
      ]),
      el("div", { className: "capture-side-column" }, [previewContainer, devicePanel.root]),
    ]),
    timeline.root,
  ]);

  refreshPreview();
  void recoverActiveJobOnMount();

  return {
    root,
    dispose: () => {
      disposed = true;
      stream?.close();
      stream = null;
    },
  };
}
