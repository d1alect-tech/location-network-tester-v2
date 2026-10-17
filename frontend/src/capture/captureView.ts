/** Представление раздела «Захват»: пошаговый визард (вариант-победитель G4)
 * — шаг 1 режим и источник, шаг 2 параметры с эхом и превью, шаг 3 запуск,
 * устройство, live-грам и журнал задачи. Мутации идут через доменный клиент
 * (nonce); занятость блокирует запуск осознанно с объявлением причины.
 * Поток запуска, восстановление задачи и машина шагов вынесены в
 * captureStartFlow/captureRecovery/captureSteps (сплит под потолок 250
 * чистых LOC); e2e-пины сохранены дуал-классами и прежними селекторами. */

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
import { createCaptureSteps } from "./captureSteps";
import type { CaptureStepsHandle } from "./captureSteps";
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
  const startRow = el("div", { className: "capture-start-row form-actions" }, [
    startButton,
    deviceRefreshButton,
  ]);

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

  // Валидация шага 2 — существующий per-mode гейт validateCaptureForm:
  // ошибки рисуются на полях, причина объявляется, фокус — на первом ошибочном.
  const validateStep2 = (): boolean => {
    const { valid, errors } = validateCaptureForm(form.values());
    if (valid !== null) {
      form.clearErrors();
      return true;
    }
    form.setErrors(errors);
    announcePolite("Форма содержит ошибки: исправьте выделенные поля.");
    form.focusFirstInvalid();
    return false;
  };

  // Визард (G4): рельс и панели шагов; шаг 3 забирает стартовую строку,
  // устройство, live-грам и хронологию (журнал и записанные сессии живут там).
  const steps: CaptureStepsHandle = createCaptureSteps({
    form: form.root,
    sections: form.sections,
    launch: [alert.line, startRow, devicePanel.root, liveGram.root, timeline.root],
    validateStep2,
    onStep: () => steps.renderEcho(form.getMode(), form.getSource()),
  });

  startButton.addEventListener("click", () => {
    const { valid } = validateCaptureForm(form.values());
    if (valid === null) {
      // Поля с ошибками живут на шаге 2: возвращаем туда и объявляем причину.
      steps.show(2);
      validateStep2();
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
  form.onChange(() => {
    refreshPreview();
    steps.renderEcho(form.getMode(), form.getSource());
  });
  const channelbar = mountCaptureChannelbar(form);

  const previewContainer = el("aside", {
    className: "capture-preview panel",
    attrs: { "aria-label": "Профиль записи" },
  });
  // Боковая колонка визарда — только превью профиля (устройство и live-грам
  // переехали на шаг 3); превью живо на всех шагах и обновляется на каждое
  // изменение формы.
  const stepMain = el("div", { className: "capture-form-column capture-step-main is-entering" }, [
    form.root,
    steps.panel3,
  ]);
  // Вход играет один раз на монтировании: переход между шагами — частое
  // действие и остаётся без анимации (моушен-правило волны).
  stepMain.addEventListener("animationend", (event) => {
    if (event.target === stepMain) stepMain.classList.remove("is-entering");
  });
  const root = el(
    "section",
    { className: "capture-view t-page", attrs: { "data-density": "default" } },
    [
      el("h2", { className: "view-title t-page", text: "Захват" }),
      el("p", {
        className: "capture-wizard-sub lnt-hint",
        text: "Три шага: режим → параметры → запуск. Журнал задачи — на шаге 3.",
      }),
      channelbar.root,
      el("div", { className: "capture-layout capture-wizard" }, [
        steps.rail,
        stepMain,
        el("div", { className: "capture-side-column" }, [previewContainer]),
      ]),
    ],
  );

  refreshPreview();
  steps.renderEcho(form.getMode(), form.getSource());
  // Deep-link билет из инспекции: если режим/источник уже решены — открываем
  // шаг 2 (пустой префилл — обычный вход с шага 1; captureParamsToPrefill
  // возвращает {} и для маршрута без параметров).
  if (opts.initial !== undefined && Object.keys(opts.initial).length > 0) steps.show(2);
  void recovery.recoverActiveJobOnMount().then((recovered) => {
    // Активная/прерванная задача: журнал и управление ею живут на шаге 3.
    if (recovered) steps.show(3);
  });

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
