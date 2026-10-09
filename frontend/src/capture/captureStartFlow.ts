/** Поток запуска записи: bootstrap с nonce, диагностика устройства с
 * preflight, старт задачи и отмена. Вынесено из captureView.ts дословно —
 * сплит под потолок 250 чистых LOC (tests/test_module_size.py). DOM здесь не
 * строится: кнопки и панели приходят от владельца. */

import type { LntApiClient } from "../api/client";
import type { DeviceApi } from "../api/client-device";
import type { JobRequest, JobSnapshot } from "../api/types-jobs";
import type { CaptureAlertHandle } from "./captureAlerts";
import type { DevicePanelHandle } from "./devicePanel";
import { busyReasonRu, initialTimeline, isActive } from "./jobTimeline";
import type { TimelineState } from "./jobTimeline";
import type { ModeFormHandle } from "./modeForm";
import type { WatchHandle } from "./sse";

/** Изменяемое состояние потока; единственный владелец — captureView. */
export interface CaptureFlowState {
  stream: WatchHandle | null;
  timelineState: TimelineState;
  lastRequest: JobRequest | null;
  disposed: boolean;
  bootstrapPromise: Promise<void> | null;
}

export interface CaptureStartFlowDeps {
  readonly client: LntApiClient;
  readonly device: DeviceApi;
  readonly devicePanel: DevicePanelHandle;
  readonly alert: CaptureAlertHandle;
  readonly form: ModeFormHandle;
  readonly startButton: HTMLButtonElement;
  readonly state: CaptureFlowState;
  /** Переносит снимок в хронологию и live-грам (оба листа знает владелец). */
  applySnapshotToTimeline(snapshot: JobSnapshot): void;
  /** Подключает SSE к задаче (реализация в captureRecovery). */
  attachStream(snapshot: JobSnapshot): void;
}

export interface CaptureStartFlowHandle {
  /** Bootstrap ровно один раз; true, когда nonce получен. */
  ensureBootstrap(): Promise<boolean>;
  /** Состояние устройства + preflight; false — причина уже показана алертом. */
  checkDeviceAndPreflight(request: JobRequest): Promise<boolean>;
  /** Старт задачи; null — повтор без сохранённого запроса (видимая причина). */
  startJob(request: JobRequest | null): Promise<void>;
  cancelJob(jobId: string): Promise<void>;
}

export function createCaptureStartFlow(deps: CaptureStartFlowDeps): CaptureStartFlowHandle {
  const { client, state } = deps;

  async function ensureBootstrap(): Promise<boolean> {
    state.bootstrapPromise ??= client
      .bootstrap()
      .then(() => undefined)
      .catch(() => undefined);
    await state.bootstrapPromise;
    return client.currentNonce !== null;
  }

  async function checkDeviceAndPreflight(request: JobRequest): Promise<boolean> {
    try {
      const deviceState = await deps.device.state();
      deps.devicePanel.renderState(deviceState);
      // Preflight выполняется всегда: блокировки должны быть reason-coded
      // даже когда устройство уже не готово (диагностика + отчёт вместе).
      const report = await deps.device.preflight(request as Parameters<DeviceApi["preflight"]>[0]);
      deps.devicePanel.renderPreflight(report);
      if (deviceState.state !== "ready") {
        deps.alert.show(
          "Запуск невозможен: устройство не готово. Выполните указанное диагностикой действие.",
          "warn",
        );
        return false;
      }
      if (!report.ready) {
        deps.alert.show(
          "Запуск невозможен: preflight нашёл блокирующие замечания — см. панель устройства.",
          "warn",
        );
        return false;
      }
      return true;
    } catch (error) {
      deps.alert.showApiError(error, state.disposed);
      return false;
    }
  }

  async function startJob(request: JobRequest | null): Promise<void> {
    if (state.disposed) return;
    deps.alert.hide();
    if (!(await ensureBootstrap())) {
      deps.alert.show("Нет связи с сервером: панель не инициализирована. Повторите попытку.");
      return;
    }
    if (isActive(state.timelineState)) {
      // Осознанная блокировка с объявленной причиной — никогда не молчаливая.
      deps.alert.show(busyReasonRu(state.timelineState) ?? "Задача ещё выполняется.", "warn");
      return;
    }
    if (request === null) {
      // U3: повтор без сохранённого запроса (например, восстановление
      // после перезапуска сервера): молчаливый возврат заменён видимой причиной.
      deps.alert.show(
        "Нет сохранённого запроса для повтора. Запустите новую запись через форму.",
        "warn",
      );
      return;
    }

    const source = deps.form.getSource();
    if (source === "device" && !(await checkDeviceAndPreflight(request))) return;

    deps.startButton.disabled = true;
    try {
      const snapshot = await client.jobs.start(request);
      state.lastRequest = request;
      state.timelineState = initialTimeline;
      deps.applySnapshotToTimeline(snapshot);
      deps.attachStream(snapshot);
    } catch (error) {
      deps.alert.showApiError(error, state.disposed);
    } finally {
      deps.startButton.disabled = false;
    }
  }

  async function cancelJob(jobId: string): Promise<void> {
    deps.alert.hide();
    try {
      const snapshot = await client.jobs.cancel(jobId);
      deps.applySnapshotToTimeline(snapshot);
    } catch (error) {
      deps.alert.showApiError(error, state.disposed);
    }
  }

  return { ensureBootstrap, checkDeviceAndPreflight, startJob, cancelJob };
}
