/** Панель спектрограммы (todo 42): сборка модели, вью и API-клиента анализа.
 * Стартовый тайл — наибольшее окно в пределах капа 524000 ячеек (обзор
 * 2048×1024 целиком не рендерится); числовая форма окна даёт ТОЧНЫЙ bbox-запрос
 * и нецветовую альтернативу DESIGN.md §4.5; гонко-защита тайлов — через
 * createTileLoader; ошибки тайла — типизированные русские баннеры с повтором. */

import type { LntApiClient } from "../../api/client";
import type { CandidateEventPayload } from "../../api/types-analysis";
import { el } from "../primitives/dom";
import { createEventList } from "./eventList";
import { createSpectrogramArtifactLoader } from "./spectrogramLoader";
import { createTileLoader, sliceTile } from "./spectrogramModel";
import type { SpectrogramLevel, TileRequest, WindowSummary } from "./spectrogramModel";
import {
  fillSessions,
  initialTileRequest,
  labeledField,
  visibleMarkerIndices,
} from "./spectrogramSetup";
import { createSpectrogramCsvControls, summarizeSliced } from "./spectrogramSummary";
import { createSpectrogramView } from "./spectrogramView";
import type { TileRenderData as TileRenderSlice } from "./spectrogramView";
import { createSpectrogramWindowForm } from "./spectrogramWindowForm";
import { TileError } from "./tileError";

const RECORDING = "спектрограмма записи";

export interface SpectrogramPanelOptions {
  client: Pick<LntApiClient, "catalogSessions" | "analysis">;
}

export interface SpectrogramPanelHandle {
  root: HTMLElement;
  destroy(): void;
}

export function createSpectrogramPanel(options: SpectrogramPanelOptions): SpectrogramPanelHandle {
  const view = createSpectrogramView();
  let level: SpectrogramLevel | null = null;
  let events: readonly CandidateEventPayload[] = [];
  /** Глобальные индексы событий, видимых в текущем тайле (связка со списком). */
  let visibleEventIds: number[] = [];
  let lastGood: TileRequest | null = null;
  let lastSummary: WindowSummary | null = null;
  /** Окно, фактически присутствующее в данных серии (для быстрого пути). */
  let renderedWindow: TileRequest["window"] | null = null;

  const status = el("p", {
    className: "lnt-spec-status",
    attrs: { role: "status" },
    text: RECORDING,
  });
  const errorBanner = el("div", {
    className: "lnt-spec-error",
    attrs: { role: "alert", hidden: "" },
  });
  const summaryHost = el("div", {
    className: "lnt-spec-summary",
    attrs: { "aria-live": "polite" },
  });

  // Повтор баннера: явное действие (загрузка каталога) или перезапрос последнего тайла.
  function showError(message: string, onRetry?: () => void): void {
    errorBanner.replaceChildren(el("p", { className: "lnt-error-text", text: message }));
    const retry = el("button", { className: "lnt-btn", text: "Повторить" });
    retry.addEventListener("click", () => {
      if (onRetry !== undefined) {
        onRetry();
        return;
      }
      if (lastGood !== null) void applyTile(lastGood);
    });
    errorBanner.append(retry);
    errorBanner.removeAttribute("hidden");
  }

  interface TileResult {
    slice: TileRenderSlice;
    summary: WindowSummary;
  }

  const loader = createTileLoader<TileResult>(async (request) => {
    if (level === null) throw new TileError("empty_window");
    // Асинхронная граница: срез считается после возможной смены поколения.
    await Promise.resolve();
    // ОДИН срез на тайл: и рендер, и сводка читают его без повторных копий.
    const slice: TileRenderSlice = sliceTile(level, request);
    return { slice, summary: summarizeSliced(slice, events) };
  });

  loader.subscribe((state) => {
    if (state.kind === "loading") {
      status.textContent = `Построение спектрограммы… (${state.request.cells} ячеек)`;
      return;
    }
    if (state.kind === "error") {
      showError(state.error instanceof Error ? state.error.message : String(state.error));
      return;
    }
    if (state.kind !== "ready") return;
    lastGood = state.request;
    lastSummary = state.value.summary;
    csv.syncCsvButtons();
    if (
      renderedWindow !== null &&
      state.request.window.t0 >= renderedWindow.t0 &&
      state.request.window.t1 <= renderedWindow.t1 &&
      state.request.window.f0 >= renderedWindow.f0 &&
      state.request.window.f1 <= renderedWindow.f1
    ) {
      // Быстрый путь: запрошенное окно уже покрыто отрисованными данными —
      // нативный зум вместо пересоздания сотен тысяч путей серии.
      view.applyWindow(
        state.request.window.t0,
        state.request.window.t1,
        state.request.window.f0,
        state.request.window.f1,
      );
    } else {
      view.renderTile(state.value.slice, state.value.summary.minDb, state.value.summary.maxDb);
      renderedWindow = { ...state.request.window };
    }
    visibleEventIds = visibleMarkerIndices(level, events, state.request);
    view.setMarkers(
      visibleEventIds.map((globalIndex) => ({
        timeS: (events[globalIndex] as CandidateEventPayload).peak_time_s,
        label: `Событие ${globalIndex + 1}: пик ${events[globalIndex]?.peak_time_s} с`,
      })),
    );
    renderSummary(state.request, state.value.summary);
  });

  async function applyTile(request: TileRequest): Promise<void> {
    errorBanner.setAttribute("hidden", "");
    await loader.load(request);
  }

  function renderSummary(request: TileRequest, summary: WindowSummary): void {
    status.textContent = `Тайл ${request.key} · ${summary.cells} ячеек`;
    status.setAttribute("data-request-key", request.key);
    status.setAttribute("data-cells", String(summary.cells));
    const format = (value: number): string =>
      value.toLocaleString("ru-RU", { maximumSignificantDigits: 6 });
    summaryHost.replaceChildren(
      el("p", {
        className: "lnt-spec-summary-line",
        text:
          `Окно: ${format(summary.tStartS)}–${format(summary.tEndS)} с · ` +
          `${format(summary.fLowHz)}–${format(summary.fHighHz)} Гц · ячеек ${summary.cells} · ` +
          `дБВ/Гц ${format(summary.minDb)}…${format(summary.maxDb)} (отн. 1 В²/Гц) · среднее ${format(summary.meanDb)} дБВ/Гц · ` +
          `без покрытия ${summary.nanShare.toFixed(4)} · событий ${summary.eventCount}`,
      }),
    );
  }

  // --- Связка маркер ↔ список (двусторонняя) -------------------------------
  const eventList = createEventList((globalIndex) => {
    const local = visibleEventIds.indexOf(globalIndex);
    if (local >= 0) view.highlightMarker(local);
  });
  view.onMarkerActivate((local) => {
    const globalIndex = visibleEventIds[local];
    if (globalIndex !== undefined) eventList.highlight(globalIndex);
  });

  // Загрузка уровня — лист spectrogramLoader (поколение + Abort + U3-ошибки).
  const artifactLoader = createSpectrogramArtifactLoader({
    client: options.client,
    showError,
    hideError: () => errorBanner.setAttribute("hidden", ""),
    resetStatus: () => {
      status.textContent = RECORDING;
    },
    applyInitialTile: async (parsed, inventoryEvents) => {
      level = parsed;
      renderedWindow = null;
      events = inventoryEvents;
      eventList.setEvents(events);
      // Домен осей строится один раз на уровень; тайлы меняют только данные.
      view.setDomain(parsed);
      await applyTile(initialTileRequest(parsed));
    },
  });

  // --- Управление: сессия, ключ артефакта, точное окно, выгрузки -----------
  const selectSession = el("select", {
    className: "lnt-select",
    attrs: { "aria-label": "Сессия спектрограммы" },
  }) as HTMLSelectElement;
  const inputKey = el("input", {
    className: "lnt-input",
    attrs: { type: "text", "aria-label": "Ключ артефакта анализа" },
  }) as HTMLInputElement;
  const buildButton = el("button", {
    className: "lnt-btn",
    text: "Построить спектрограмму",
    attrs: { type: "button" },
  });
  buildButton.addEventListener("click", () => {
    if (selectSession.value !== "" && inputKey.value.trim() !== "")
      void artifactLoader.load(selectSession.value, inputKey.value.trim());
    else showError("Укажите сессию и ключ артефакта анализа.");
  });

  // Числовая форма окна — лист spectrogramWindowForm (точный bbox-запрос).
  const windowForm = createSpectrogramWindowForm({
    getLevel: () => level,
    applyTile,
    showError,
  });
  view.onWindowChange((t0s, t1s, f0hz, f1hz) => {
    windowForm.syncFromWindow(t0s, t1s, f0hz, f1hz);
  });

  // Выгрузки CSV — лист spectrogramSummary (кнопки + sync + U3-no-op причины).
  const csv = createSpectrogramCsvControls({
    getLevel: () => level,
    getLastGood: () => lastGood,
    getLastSummary: () => lastSummary,
    showError,
  });

  const controls = el("div", { className: "lnt-workbench-controls lnt-spec-controls" }, [
    labeledField("Сессия", selectSession),
    labeledField("Ключ артефакта", inputKey),
    buildButton,
    ...windowForm.fields,
    csv.matrixButton,
    csv.summaryButton,
    csv.csvHint,
  ]);

  const root = el("section", { className: "lnt-spec-panel" }, [
    el("h3", { className: "lnt-chart-title", text: RECORDING }),
    controls,
    status,
    errorBanner,
    summaryHost,
    view.root,
    eventList.root,
  ]);

  // Загрузка каталога с видимой ошибкой и повтором вместо молчаливого пустого селекта.
  function loadSessions(): void {
    errorBanner.setAttribute("hidden", "");
    void options.client
      .catalogSessions()
      .then((page) => fillSessions(selectSession, page.items, "Выберите сессию"))
      .catch(() => showError("Не удалось загрузить список сессий.", loadSessions));
  }
  loadSessions();

  return {
    root,
    destroy: () => {
      loader.dispose();
      view.dispose();
      root.remove();
    },
  };
}
