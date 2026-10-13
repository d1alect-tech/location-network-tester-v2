/** Рабочая область «Спектроанализатор» (#/sa, Todo 14): статус устройства
 * и владения (GET /api/device/state, GET /api/live/state + heartbeat SSE),
 * Run/Stop с nonce (старт берёт прибор дефолтом, если не запущен; уже
 * запущенный поток НЕ перезапускается — вкладка присоединяется к нему,
 * настроив SA-контур POST /api/live/config с SA-конфигурацией). Трассы
 * события spectrum считает клиентский склад (saTraceStore): сервер трасс
 * не хранит. Правило остановки: размонтирование закрывает подписку, но НЕ
 * останавливает захват — авто-stop при выходе из группы маршрутов
 * {scope, sa} делает AppShell (client-live.LIVE_ROUTE_GROUP). */

import type { LntApiClient } from "../../api/client";
import { createDeviceApi } from "../../api/client-device";
import { sharedLiveApi } from "../../api/client-live";
import type { LiveApi } from "../../api/client-live";
import type { LiveSaConfig, LiveStatePayload } from "../../api/types-live";
import { DEFAULT_LIVE_SA_CONFIG, DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import {
  LIVE_STATE_TEXT,
  buildSaReadoutSection,
  buildSaStatusSection,
  errorBlock,
} from "./saSections";
import { buildSaConfigSection } from "./saSelectors";
import { mountSaSpectrum } from "./saSpectrum";
import type { SaSpectrumOptions } from "./saSpectrum";
import { buildSaTraceControls } from "./saTraceControls";
import { SaTraceStore } from "./saTraceStore";
import "./sa.css";
export interface SaWorkspaceOptions {
  client: LntApiClient;
  /** Live-контур; по умолчанию — общий singleton (осциллограф + анализатор). */
  live?: LiveApi;
  /** Шов рендера спектра: тесты подменяют фабрику графика. */
  spectrum?: SaSpectrumOptions;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function mountSaWorkspace(container: HTMLElement, options: SaWorkspaceOptions): () => void {
  const live = options.live ?? sharedLiveApi();
  const device = createDeviceApi(options.client);
  const store = new SaTraceStore();
  let saConfig: LiveSaConfig = { ...DEFAULT_LIVE_SA_CONFIG };
  const selectors = buildSaConfigSection({
    initial: saConfig,
    onChange: (config) => {
      saConfig = config;
      // Живой захват — селекторы уходят на ходу (POST /api/live/config);
      // без захвата панель стейджится до следующего запуска.
      if (lastState?.state === "running") void configSa();
    },
  });
  const traceControls = buildSaTraceControls({
    onClear: () => {
      store.clear();
      spectrum.rerender(viewOptions());
    },
    onViewChange: () => {
      spectrum.rerender(viewOptions());
    },
  });
  const spectrum = mountSaSpectrum({
    createView: options.spectrum?.createView,
    controls: traceControls.root,
  });
  const status = buildSaStatusSection();
  const readout = buildSaReadoutSection();

  container.append(
    el(
      "div",
      {
        className: "lnt-sa-workspace",
        attrs: { role: "region", "aria-label": "Спектроанализатор" },
      },
      [
        el("h2", { className: "placeholder-title t-page", text: "Спектроанализатор" }),
        status.root,
        selectors.root,
        spectrum.root,
        readout.root,
      ],
    ),
  );

  let busy = false;
  let lastState: LiveStatePayload | null = null;
  /** SA-контур настроен для текущего захвата (join/конфиг уже ушёл). */
  let saApplied = false;

  function viewOptions() {
    return {
      unit: traceControls.unit(),
      xLog: traceControls.xLog(),
      traces: traceControls.visibleTraces(),
    };
  }

  function updateButtons(): void {
    const running = lastState?.state === "running";
    status.runButton.disabled = busy || running;
    status.stopButton.disabled = busy || !running;
  }

  function applyState(state: LiveStatePayload): void {
    lastState = state;
    status.stateLine.setAttribute("data-live-state", state.state);
    status.stateLine.textContent = `Живой режим: ${LIVE_STATE_TEXT[state.state]}`;
    status.simBadge.hidden = state.mode !== "sim";
    status.busyLine.hidden = state.busy_reason === null;
    if (state.busy_reason !== null) status.busyLine.textContent = state.busy_reason;
    if (state.state === "running") ensureSaConfig();
    else saApplied = false;
    updateButtons();
  }

  function showError(text: string): void {
    clearElement(status.errorHost);
    status.errorHost.append(errorBlock(text));
    announcePolite(text);
  }

  /** Присоединение: SA-контур настраивается ровно один раз на захват. */
  function ensureSaConfig(): void {
    if (lastState?.state !== "running" || saApplied || busy) return;
    saApplied = true;
    void configSa();
  }

  /** SA-конфиг на ходу: триггер зеркалом состояния сервиса (не свой). */
  async function configSa(): Promise<void> {
    clearElement(status.errorHost);
    const trigger = lastState?.trigger ?? DEFAULT_LIVE_START_REQUEST.trigger;
    try {
      applyState(await live.updateConfig({ ...trigger, sa: saConfig }));
    } catch (error) {
      showError(`Не удалось применить настройки SA: ${messageOf(error)}.`);
    }
  }

  async function refreshDevice(): Promise<void> {
    clearElement(status.deviceHost);
    status.deviceHost.append(el("p", { className: "t-compact", text: "Проверка устройства…" }));
    try {
      const deviceState = await device.state();
      clearElement(status.deviceHost);
      status.deviceHost.append(
        el("p", {
          className: "t-compact",
          text: `Устройство: ${deviceState.state} — ${deviceState.description_ru}`,
        }),
      );
    } catch (error) {
      clearElement(status.deviceHost);
      status.deviceHost.append(
        errorBlock(`Не удалось получить состояние устройства: ${messageOf(error)}.`),
      );
    }
  }

  async function runLive(): Promise<void> {
    const config = selectors.config();
    if (config === null) {
      showError("Запуск отклонён: полоса SA некорректна.");
      return;
    }
    saConfig = config;
    busy = true;
    updateButtons();
    clearElement(status.errorHost);
    try {
      // Уже запущенный поток (осциллограф) НЕ перезапускается — вкладка
      // присоединяется к нему, дальше SA-контур настраивается конфигом.
      if (lastState?.state !== "running") {
        applyState(await live.start({ ...DEFAULT_LIVE_START_REQUEST }));
      }
      announcePolite("Живой режим запущен");
    } catch (error) {
      showError(`Не удалось запустить живой режим: ${messageOf(error)}.`);
    } finally {
      busy = false;
      updateButtons();
      ensureSaConfig();
    }
  }

  async function stopLive(): Promise<void> {
    busy = true;
    updateButtons();
    clearElement(status.errorHost);
    try {
      applyState(await live.stop());
      announcePolite("Живой режим остановлен");
    } catch (error) {
      showError(`Не удалось остановить живой режим: ${messageOf(error)}.`);
    } finally {
      busy = false;
      updateButtons();
    }
  }

  status.runButton.addEventListener("click", () => void runLive());
  status.stopButton.addEventListener("click", () => void stopLive());

  // Подписка до старта разрешена (routes_live.py): без захвата приходят
  // heartbeat-события со статусом владения — вкладка жива и до Run.
  const stream = live.watchFrames({
    onSpectrum: (payload) => {
      const applied = store.applyTrace(payload.freq, payload.psd_db);
      if (!applied) {
        spectrum.showProblem();
        return;
      }
      spectrum.applyStore(store, viewOptions());
      readout.applySpectrum(payload, store.sweepCount());
    },
    onState: applyState,
    onConnection: (kind) => {
      readout.connection.textContent = kind === "live" ? "передача данных" : "переподключение…";
    },
  });

  void refreshDevice();
  void live.state().then(applyState, (error: unknown) => {
    showError(`Не удалось получить статус живого режима: ${messageOf(error)}.`);
  });

  return () => {
    // Только подписка: авто-stop — решение AppShell по группе маршрутов.
    stream.close();
    spectrum.destroy();
  };
}
