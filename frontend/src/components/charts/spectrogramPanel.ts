/** Панель спектрограммы (todo 42): сборка модели, вью и API-клиента анализа.
 * Стартовый тайл — наибольшее окно в пределах капа 524000 ячеек (обзор
 * 2048×1024 целиком не рендерится); числовая форма окна даёт ТОЧНЫЙ bbox-запрос
 * и нецветовую альтернативу DESIGN.md §4.5; гонко-защита тайлов — через
 * createTileLoader; ошибки тайла — типизированные русские баннеры с повтором. */

import type { LntApiClient } from "../../api/client";
import type { CandidateEventPayload } from "../../api/types-analysis";
import { el } from "../primitives/dom";
import { downloadCsv } from "./csvDownload";
import { createEventList } from "./eventList";
import { readNpzArrays } from "./npz";
import { createTileLoader, sliceTile, tileRequestForRange } from "./spectrogramModel";
import type { SpectrogramLevel, TileRequest, WindowSummary } from "./spectrogramModel";
import {
  fillSessions,
  initialTileRequest,
  labeledField,
  levelFromNpz,
  numberInput,
  visibleMarkerIndices,
} from "./spectrogramSetup";
import { summarizeSliced, summaryCsv, tileMatrixCsv } from "./spectrogramSummary";
import { createSpectrogramView } from "./spectrogramView";
import type { TileRenderData as TileRenderSlice } from "./spectrogramView";
import { TileError } from "./tileError";

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
  let loadGeneration = 0;
  let loadAbort = new AbortController();
  /** Окно, фактически присутствующее в данных серии (для быстрого пути). */
  let renderedWindow: TileRequest["window"] | null = null;

  const status = el("p", {
    className: "lnt-spec-status",
    attrs: { role: "status" },
    text: "Выберите сессию и введите ключ артефакта анализа.",
  });
  const errorBanner = el("div", {
    className: "lnt-spec-error",
    attrs: { role: "alert", hidden: "" },
  });
  const summaryHost = el("div", {
    className: "lnt-spec-summary",
    attrs: { "aria-live": "polite" },
  });

  function showError(message: string): void {
    errorBanner.replaceChildren(el("p", { className: "lnt-error-text", text: message }));
    const retry = el("button", { className: "lnt-btn", text: "Повторить" });
    retry.addEventListener("click", () => {
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
    visibleEventIds = markerIndices(state.request);
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

  function markerIndices(request: TileRequest): number[] {
    return visibleMarkerIndices(level, events, request);
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
          `дБ ${format(summary.minDb)}…${format(summary.maxDb)} · среднее ${format(summary.meanDb)} дБ · ` +
          `без покрытия ${summary.nanShare.toFixed(4)} · событий ${summary.eventCount}`,
      }),
    );
  }

  async function loadArtifact(session: string, key: string): Promise<void> {
    // Гонко-защита загрузки уровня (паттерн createTileLoader): устаревший
    // ответ отбрасывается по поколению, прежний полёт обрывается Abort'ом.
    const generation = ++loadGeneration;
    loadAbort.abort();
    loadAbort = new AbortController();
    const signal = loadAbort.signal;
    errorBanner.setAttribute("hidden", "");
    status.textContent = "Загрузка спектрограммы…";
    try {
      const [bytes, inventory] = await Promise.all([
        options.client.analysis.artifactBytes(session, key, "spectrogram.npz", { signal }),
        options.client.analysis.events(session, key, { signal }),
      ]);
      if (generation !== loadGeneration) return; // устаревшая загрузка — игнорируем
      const parsed = levelFromNpz(
        await readNpzArrays(bytes, ["time_s", "frequency_hz", "power_db"]),
      );
      level = parsed;
      renderedWindow = null;
      events = inventory.events;
      eventList.setEvents(events);
      // Домен осей строится один раз на уровень; тайлы меняют только данные.
      view.setDomain(parsed);
      await applyTile(initialTileRequest(parsed));
    } catch (error) {
      if (generation !== loadGeneration || isAbort(error)) return;
      showError(error instanceof Error ? error.message : String(error));
    }
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
    if (selectSession.value === "" || inputKey.value.trim() === "") {
      showError("Укажите сессию и ключ артефакта анализа.");
      return;
    }
    void loadArtifact(selectSession.value, inputKey.value.trim());
  });

  // Числовая форма окна — ТОЧНЫЙ bbox-запрос и нецветовая альтернатива матрице.
  const tStart = numberInput("Начало окна, с");
  const tEnd = numberInput("Конец окна, с");
  const fLow = numberInput("Нижняя граница окна, Гц");
  const fHigh = numberInput("Верхняя граница окна, Гц");
  const applyWindowButton = el("button", {
    className: "lnt-btn lnt-btn-small",
    text: "Обновить окно",
    attrs: { type: "button" },
  });
  applyWindowButton.addEventListener("click", () => {
    if (level === null) {
      showError("Сначала постройте спектрограмму.");
      return;
    }
    try {
      void applyTile(
        tileRequestForRange(
          level,
          Number(tStart.value),
          Number(tEnd.value),
          Number(fLow.value),
          Number(fHigh.value),
        ),
      );
    } catch (error) {
      showError(error instanceof Error ? error.message : String(error));
    }
  });
  view.onWindowChange((t0s, t1s, f0hz, f1hz) => {
    tStart.value = String(t0s);
    tEnd.value = String(t1s);
    fLow.value = String(f0hz);
    fHigh.value = String(f1hz);
  });

  const matrixButton = el("button", {
    className: "lnt-btn lnt-btn-small",
    text: "Скачать матрицу CSV",
    attrs: { type: "button" },
  });
  matrixButton.addEventListener("click", () => {
    if (level === null || lastGood === null) return;
    downloadCsv(`spectrogram-${lastGood.key}.csv`, tileMatrixCsv(level, lastGood));
  });
  const summaryButton = el("button", {
    className: "lnt-btn lnt-btn-small",
    text: "Скачать сводку CSV",
    attrs: { type: "button" },
  });
  summaryButton.addEventListener("click", () => {
    if (lastSummary === null) return;
    downloadCsv("spectrogram-summary.csv", summaryCsv(lastSummary));
  });

  const controls = el("div", { className: "lnt-workbench-controls lnt-spec-controls" }, [
    labeledField("Сессия", selectSession),
    labeledField("Ключ артефакта", inputKey),
    buildButton,
    labeledField("Начало, с", tStart),
    labeledField("Конец, с", tEnd),
    labeledField("От, Гц", fLow),
    labeledField("До, Гц", fHigh),
    applyWindowButton,
    matrixButton,
    summaryButton,
  ]);

  const root = el("section", { className: "lnt-spec-panel" }, [
    el("h3", { className: "lnt-chart-title", text: "Спектрограмма (STFT)" }),
    controls,
    status,
    errorBanner,
    summaryHost,
    view.root,
    eventList.root,
  ]);

  void options.client
    .catalogSessions()
    .then((page) => fillSessions(selectSession, page.items, "Выберите сессию"))
    .catch(() => {
      /* Каталог недоступен: селект остаётся с подсказкой выбора. */
    });

  return {
    root,
    destroy: () => {
      loader.dispose();
      view.dispose();
      root.remove();
    },
  };
}

function isAbort(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: unknown }).name === "AbortError"
  );
}
