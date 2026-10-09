/** Представление раздела «Захват»: mode-first форма, предпросмотр профиля,
 * диагностика устройства с preflight, хронология задачи через SSE.
 * Мутации идут через доменный клиент (nonce); занятость блокирует запуск
 * осознанно с объявлением причины. Поток запуска и восстановление задачи
 * вынесены в captureStartFlow/captureRecovery (сплит под потолок 250 чистых
 * LOC); разметка раздела и его поведение не менялись. */

import type { LntApiClient } from "../api/client";
import { createDeviceApi } from "../api/client-device";
import type { JobSnapshot } from "../api/types-jobs";
import { el } from "../components/primitives/dom";
import { announcePolite } from "../components/primitives/status";
import { createCaptureAlert } from "./captureAlerts";
import type { CaptureAlertHandle } from "./captureAlerts";
import { applyCapturePrefill } from "./captureDeepLink";
import type { CapturePrefill } from "./captureDeepLink";
import { createCaptureRecovery } from "./captureRecovery";
import { createCaptureStartFlow } from "./captureStartFlow";
import type { CaptureFlowState, CaptureStartFlowHandle } from "./captureStartFlow";
import { mountCaptureChannelbar } from "./channelbarCapture";
import { createDevicePanel } from "./devicePanel";
import type { DevicePanelHandle } from "./devicePanel";
import { applySnapshot, initialTimeline } from "./jobTimeline";
import { createJobTimelineView } from "./jobTimelineView";
import type { TimelineViewHandle } from "./jobTimelineView";
import { createModeForm } from "./modeForm";
import type { ModeFormHandle } from "./modeForm";
import { buildJobRequest, validateCaptureForm } from "./modes";
import { renderProfilePreview } from "./profilePreview";
import { createSpectrogramLivePanel } from "./spectrogramLivePanel";
import type { LivePanelHandle } from "./spectrogramLivePanel";

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
  const state: CaptureFlowState = {
    stream: null,
    timelineState: initialTimeline,
    lastRequest: null,
    disposed: false,
    bootstrapPromise: null,
  };

  // Цикл сборки: хронология зовёт поток запуска, а поток запуска пишет в
  // хронологию. Ячейка заполняется один раз ниже, до любого действия
  // оператора; обращение до заполнения — явная ошибка, а не молчаливый no-op.
  const startFlowSlot: { current: CaptureStartFlowHandle | null } = { current: null };
  const startFlowOf = (): CaptureStartFlowHandle => {
    const flow = startFlowSlot.current;
    if (flow === null) throw new Error("поток запуска захвата не собран");
    return flow;
  };
  const timeline: TimelineViewHandle = createJobTimelineView({
    onCancel: (jobId) => void startFlowOf().cancelJob(jobId),
    onRetry: () => void startFlowOf().startJob(state.lastRequest),
  });

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
    state.timelineState = applySnapshot(state.timelineState, snapshot);
    timeline.update(state.timelineState);
    liveGram.onSnapshot(snapshot);
  };

  const recovery = createCaptureRecovery({
    client,
    state,
    timeline,
    liveGram,
    applySnapshotToTimeline,
    ensureBootstrap: () => startFlowOf().ensureBootstrap(),
  });
  startFlowSlot.current = createCaptureStartFlow({
    client,
    device,
    devicePanel,
    alert,
    form,
    startButton,
    state,
    applySnapshotToTimeline,
    attachStream: recovery.attachStream,
  });

  startButton.addEventListener("click", () => {
    const { valid, errors } = validateCaptureForm(form.values());
    if (valid === null) {
      form.setErrors(errors);
      announcePolite("Форма содержит ошибки: исправьте выделенные поля.");
      return;
    }
    form.clearErrors();
    void startFlowOf().startJob(buildJobRequest(form.getMode(), valid, form.getSource()));
  });
  deviceRefreshButton.addEventListener("click", () => {
    void startFlowOf()
      .ensureBootstrap()
      .then(async () => {
        try {
          devicePanel.renderState(await device.state());
        } catch (error) {
          alert.showApiError(error, state.disposed);
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
  void recovery.recoverActiveJobOnMount();

  return {
    root,
    dispose: () => {
      state.disposed = true;
      state.stream?.close();
      state.stream = null;
      liveGram.dispose();
    },
  };
}
