/** Представление раздела «Захват»: mode-first форма, предпросмотр профиля,
 * диагностика устройства с preflight, хронология задачи через SSE.
 * Мутации идут через доменный клиент (nonce); занятость блокирует запуск
 * осознанно с объявлением причины. */

import type { LntApiClient } from "../api/client";
import { createDeviceApi } from "../api/client-device";
import type { JobRequest, JobSnapshot } from "../api/types-jobs";
import { el } from "../components/primitives/dom";
import { announcePolite } from "../components/primitives/status";
import { createCaptureAlert } from "./captureAlerts";
import type { CaptureAlertHandle } from "./captureAlerts";
import { applyCapturePrefill } from "./captureDeepLink";
import type { CapturePrefill } from "./captureDeepLink";
import { mountCaptureChannelbar } from "./channelbarCapture";
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
import { createSpectrogramLivePanel } from "./spectrogramLivePanel";
import type { LivePanelHandle } from "./spectrogramLivePanel";
import { watchJobEvents } from "./sse";
import type { WatchHandle } from "./sse";

export interface CaptureViewHandle {
  root: HTMLElement;
  /** Закрывает SSE и обрывает незавершённые запросы (уход с маршрута). */
  dispose(): void;
}

export interface CaptureViewOptions {
  /** Префилл из deep-link билета (C1): мусор уже отсеян captureParamsToPrefill. */
  readonly initial?: CapturePrefill;
}

export type { CaptureAlertTone } from "./captureAlerts";

export function createCaptureView(
  client: LntApiClient,
  opts: CaptureViewOptions = {},
): CaptureViewHandle {
  const device = createDeviceApi(client);
  const form: ModeFormHandle = createModeForm();
  if (opts.initial !== undefined) applyCapturePrefill(form.root, opts.initial);
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

  const alert: CaptureAlertHandle = createCaptureAlert();
  const liveGram: LivePanelHandle = createSpectrogramLivePanel({ plots: client.plots });

  const startButton = el("button", {
    className: "lnt-btn lnt-btn-primary btn",
    text: "Запустить запись",
    attrs: { type: "button" },
  }) as HTMLButtonElement;
  const deviceRefreshButton = el("button", {
    className: "lnt-btn btn-quiet",
    text: "Проверить устройство",
    attrs: { type: "button" },
  }) as HTMLButtonElement;

  const refreshPreview = (): void => {
    alert.hide();
    renderProfilePreview(previewContainer, form.getMode(), form.values(), form.getSource());
  };

  const applySnapshotToTimeline = (snapshot: JobSnapshot): void => {
    timelineState = applySnapshot(timelineState, snapshot);
    timeline.update(timelineState);
    liveGram.onSnapshot(snapshot);
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
        alert.show(
          "Запуск невозможен: устройство не готово. Выполните указанное диагностикой действие.",
          "warn",
        );
        return false;
      }
      if (!report.ready) {
        alert.show(
          "Запуск невозможен: preflight нашёл блокирующие замечания — см. панель устройства.",
          "warn",
        );
        return false;
      }
      return true;
    } catch (error) {
      alert.showApiError(error, disposed);
      return false;
    }
  }

  async function startJob(request: JobRequest | null): Promise<void> {
    if (disposed) return;
    alert.hide();
    if (!(await ensureBootstrap())) {
      alert.show("Нет связи с сервером: панель не инициализирована. Повторите попытку.");
      return;
    }
    if (isActive(timelineState)) {
      // Осознанная блокировка с объявленной причиной — никогда не молчаливая.
      alert.show(busyReasonRu(timelineState) ?? "Задача ещё выполняется.", "warn");
      return;
    }
    if (request === null) {
      // U3: повтор без сохранённого запроса (например, восстановление
      // после перезапуска сервера): молчаливый возврат заменён видимой причиной.
      alert.show(
        "Нет сохранённого запроса для повтора. Запустите новую запись через форму.",
        "warn",
      );
      return;
    }

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
      alert.showApiError(error, disposed);
    } finally {
      startButton.disabled = false;
    }
  }

  async function cancelJob(jobId: string): Promise<void> {
    alert.hide();
    try {
      const snapshot = await client.jobs.cancel(jobId);
      applySnapshotToTimeline(snapshot);
    } catch (error) {
      alert.showApiError(error, disposed);
    }
  }

  async function recoverActiveJobOnMount(): Promise<void> {
    if (!(await ensureBootstrap())) return;
    try {
      const page = await client.jobs.list(1, 0);
      const latest = page.items[0];
      // Live-панель в idle показывает последнюю завершённую сессию post-hoc.
      if (latest !== undefined) liveGram.onSnapshot(latest);
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
        alert.showApiError(error, disposed);
      }
    });
  });
  form.onChange(refreshPreview);
  const channelbar = mountCaptureChannelbar(form);

  const previewContainer = el("aside", {
    className: "capture-preview panel",
    attrs: { "aria-label": "Профиль записи" },
  });
  const root = el("section", { className: "capture-view t-page" }, [
    el("h2", { className: "view-title t-page", text: "Захват" }),
    channelbar.root,
    el("div", { className: "capture-layout" }, [
      el("div", { className: "capture-form-column" }, [
        form.root,
        alert.line,
        el("div", { className: "capture-start-row form-actions" }, [
          startButton,
          deviceRefreshButton,
        ]),
      ]),
      el("div", { className: "capture-side-column" }, [
        previewContainer,
        devicePanel.root,
        liveGram.root,
      ]),
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
      liveGram.dispose();
    },
  };
}
