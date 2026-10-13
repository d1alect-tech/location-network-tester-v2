/** Рабочая область «Осциллограф» (#/scope, Todo 7 — скелет live-режима;
 * Todo 8 — живая развёртка): статус устройства (GET /api/device/state) и
 * владения (GET /api/live/state + heartbeat SSE), Run/Stop (POST с nonce;
 * тело запуска несёт выбранные В/дел и пробник из селекторов развёртки),
 * показания потока из кадров и рендер кадров общим uPlot-стеком
 * (scopeWaveform). Правило остановки: размонтирование закрывает подписку,
 * но НЕ останавливает захват — авто-stop при выходе из группы маршрутов
 * {scope, sa} делает AppShell (client-live.LIVE_ROUTE_GROUP). */

import type { LntApiClient } from "../../api/client";
import { createDeviceApi } from "../../api/client-device";
import { sharedLiveApi } from "../../api/client-live";
import type { LiveApi } from "../../api/client-live";
import type { LiveStatePayload } from "../../api/types-live";
import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import { createUplotView } from "../../components/charts/uplotView";
import { clearElement, el } from "../../components/primitives/dom";
import { announcePolite } from "../../components/primitives/status";
import { buildScopeControls } from "./scopeControls";
import { buildScopeCursorSection } from "./scopeCursorSection";
import { DEFAULT_SCOPE_SETTINGS } from "./scopeScale";
import type { ScopeDisplaySettings } from "./scopeScale";
import { buildScopeScreen } from "./scopeScreen";
import {
  LIVE_STATE_TEXT,
  buildScopeMeasureSection,
  buildScopeReadoutSection,
  buildScopeStatusSection,
  errorBlock,
} from "./scopeSections";
import { mountScopeWaveform } from "./scopeWaveform";
import type { ScopeWaveformOptions } from "./scopeWaveform";
import "./scope.css";

export interface ScopeWorkspaceOptions {
  client: LntApiClient;
  /** Live-контур; по умолчанию — общий singleton (осциллограф + анализатор). */
  live?: LiveApi;
  /** Шов рендера развёртки: тесты подменяют хэндл графика. */
  waveform?: ScopeWaveformOptions;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function mountScopeWorkspace(
  container: HTMLElement,
  options: ScopeWorkspaceOptions,
): () => void {
  const live = options.live ?? sharedLiveApi();
  const device = createDeviceApi(options.client);
  const status = buildScopeStatusSection();
  const screen = buildScopeScreen();
  const cursors = buildScopeCursorSection();
  const measure = buildScopeMeasureSection();
  const readout = buildScopeReadoutSection();

  let settings: ScopeDisplaySettings = { ...DEFAULT_SCOPE_SETTINGS };
  const controls = buildScopeControls((next) => {
    settings = next;
    // Последний кадр перерисовывается под новые настройки; V/div и пробник
    // уходят в железо со следующим Run (config на ходу меняет только триггер).
    waveform.rerender(settings);
  });
  // Шов createView пробрасывает плагин линий курсоров (Todo 10) в общий
  // стек uPlot: плагин живёт в каждой пересборке графика.
  const waveform = mountScopeWaveform({
    createView: (viewOptions) =>
      (options.waveform?.createView ?? createUplotView)({
        ...viewOptions,
        peaksPlugin: cursors.plugin,
      }),
    controls: controls.root,
  });

  container.append(
    el(
      "div",
      { className: "lnt-scope-workspace", attrs: { role: "region", "aria-label": "Осциллограф" } },
      [
        el("h2", { className: "placeholder-title t-page", text: "Осциллограф" }),
        status.root,
        screen.root,
        waveform.root,
        cursors.root,
        measure.root,
        readout.root,
      ],
    ),
  );

  let busy = false;
  let lastState: LiveStatePayload | null = null;
  /** Порог фронта для измерений: уровень триггера, пока его источник CH1. */
  let triggerLevelV: number | null = null;

  function updateButtons(): void {
    const running = lastState?.state === "running";
    status.runButton.disabled = busy || running;
    status.stopButton.disabled = busy || !running;
  }

  function applyState(state: LiveStatePayload): void {
    lastState = state;
    triggerLevelV =
      state.trigger !== null && state.trigger.source === "ch1" ? state.trigger.level_v : null;
    status.stateLine.setAttribute("data-live-state", state.state);
    status.stateLine.textContent = `Живой режим: ${LIVE_STATE_TEXT[state.state]}`;
    status.simBadge.hidden = state.mode !== "sim";
    status.busyLine.hidden = state.busy_reason === null;
    if (state.busy_reason !== null) status.busyLine.textContent = state.busy_reason;
    updateButtons();
  }

  function showError(text: string): void {
    clearElement(status.errorHost);
    status.errorHost.append(errorBlock(text));
    announcePolite(text);
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
    busy = true;
    updateButtons();
    clearElement(status.errorHost);
    try {
      applyState(
        await live.start({
          ...DEFAULT_LIVE_START_REQUEST,
          // V/div и пробник из селекторов развёртки; триггер — зеркало дефолтов.
          ch1_range_v: settings.vDiv,
          ch1_probe_multiplier: settings.probe,
        }),
      );
      announcePolite("Живой режим запущен");
    } catch (error) {
      showError(`Не удалось запустить живой режим: ${messageOf(error)}.`);
    } finally {
      busy = false;
      updateButtons();
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
    onFrame: (frame) => {
      readout.applyFrame(frame);
      screen.applyFrame(frame);
      waveform.applyFrame(frame, settings);
      cursors.applyFrame(frame);
      measure.applyFrame(frame, triggerLevelV);
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
    screen.dispose();
    waveform.destroy();
  };
}
