/** Панель «Маркеры и пики» SA (Todo 15): постановка маркеров по клику
 * на спектре (до 4, дальше видимый отказ), таблица маркеров с отсчётом
 * (частота + уровень по живой трассе) и поиск пиков текущей трассы —
 * кнопка снимает peaks[] последнего свипа в таблицу и подсветку графика
 * (как peaksFromDetail инспекции). Маркеры и снимок живут только на
 * клиенте: панель ничего не отправляет, склад/сеть не трогает.
 * Панельная система V6 (kit.css §5.2), токены — sa.css. */

import type { LiveSaPeak } from "../../api/types-live";
import type { ChartPeak } from "../../components/charts/types";
import { el } from "../../components/primitives/dom";
import { peakRow, tableHead } from "./saMarkerRows";
import { SaMarkers, peaksFromSweep } from "./saMarkers";
import type { SaMarkerRejectReason } from "./saMarkers";
import type { SaMarkerLine } from "./saSpectrum";
import type { SaTraceStore } from "./saTraceStore";
import { formatDb, formatHz } from "./saUnits";

const REJECT_TEXT: Record<SaMarkerRejectReason, string> = {
  limit: "Маркер не поставлен: максимум 4.",
  "no-trace": "Маркер не поставлен: нет трассы для отсчёта.",
};

const MARKERS_EMPTY = "Маркеры не поставлены: клик по спектру ставит маркер (до 4).";
const PEAKS_EMPTY = "Пики не искались: «Найти пики» отметит максимумы текущей трассы.";
const PEAKS_NONE = "Выраженных пиков в текущей трассе не найдено.";

export interface SaMarkerPanelDeps {
  /** Склад трасс: живая трасса (clear) — источник отсчёта уровня. */
  store: SaTraceStore;
  /** Пики последнего свипа: сервер уже отобрал максимумы по prominence. */
  sweepPeaks(): readonly LiveSaPeak[];
  /** Перерисовка спектра после смены маркеров/подсветки. */
  rerender(): void;
  redraw?(): void;
}

export interface SaMarkerPanelView {
  readonly root: HTMLElement;
  readonly tools: HTMLElement;
  readonly peakSearch: HTMLButtonElement;
  readonly markersClear: HTMLButtonElement;
  /** Маркеры для плагина отрисовки графика (M1..M4). */
  markerLines(): readonly SaMarkerLine[];
  /** Снимок пиков поиска для подсветки графика. */
  peakHighlight(): readonly ChartPeak[];
  /** Клик по полю графика: постановка маркера с отсчётом. */
  placeMarker(frequencyHz: number): void;
  selectMarker(id: number): void;
  moveMarker(id: number, frequencyHz: number): void;
  removeMarker(id: number): void;
  refreshFromStore(): void;
}

export function buildSaMarkerPanel(deps: SaMarkerPanelDeps): SaMarkerPanelView {
  const markers = new SaMarkers();
  let selected: number | null = null;
  let highlight: readonly ChartPeak[] = [];

  const peakSearchButton = el("button", {
    className: "btn",
    text: "Найти пики",
    attrs: { type: "button", id: "lnt-sa-peak-search" },
  });
  peakSearchButton.addEventListener("click", () => {
    const raw = deps.sweepPeaks();
    highlight = peaksFromSweep(raw);
    peakBody.replaceChildren(...raw.map(peakRow));
    peakEmpty.textContent = raw.length === 0 ? PEAKS_NONE : PEAKS_EMPTY;
    peakEmpty.hidden = raw.length > 0;
    peakTable.hidden = raw.length === 0;
    deps.rerender();
  });

  const clearButton = el("button", {
    className: "btn btn-secondary",
    text: "Убрать маркеры",
    attrs: { type: "button", id: "lnt-sa-markers-clear" },
  });
  clearButton.addEventListener("click", () => {
    markers.clear();
    applyMarkers();
    deps.rerender();
  });

  const notice = el("p", {
    className: "t-compact lnt-sa-marker-notice",
    attrs: { role: "status" },
  });
  notice.hidden = true;

  const markerEmpty = el("p", {
    className: "t-compact lnt-sa-table-empty",
    text: MARKERS_EMPTY,
    attrs: { "data-sa-markers-empty": "" },
  });
  const markerTable = el("table", { className: "lnt-sa-table", attrs: { "data-sa-markers": "" } });
  markerTable.append(tableHead(["Маркер", "Частота", "Уровень, дБ"]));
  markerTable.querySelector("thead tr")?.append(el("th", { attrs: { "aria-label": "Удалить" } }));
  const markerBody = el("tbody");
  markerTable.append(markerBody);
  markerTable.hidden = true;

  const peakEmpty = el("p", {
    className: "t-compact lnt-sa-table-empty",
    text: PEAKS_EMPTY,
    attrs: { "data-sa-peaks-empty": "" },
  });
  const peakTable = el("table", { className: "lnt-sa-table", attrs: { "data-sa-peaks": "" } });
  peakTable.append(tableHead(["Частота", "Уровень, дБ", "Превышение, дБ", "Q"]));
  const peakBody = el("tbody");
  peakTable.append(peakBody);
  peakTable.hidden = true;

  function applyMarkers(): void {
    const list = markers.list();
    markerBody.replaceChildren(
      ...list.map((marker) => {
        const select = el("button", {
          className: "lnt-sa-marker-select",
          text: `M${marker.id}`,
          attrs: {
            type: "button",
            "aria-pressed": String(marker.id === selected),
            "aria-label": `Выбрать M${marker.id}`,
          },
        });
        select.addEventListener("click", () => view.selectMarker(marker.id));
        const frequency = el("input", {
          className: "lnt-sa-marker-frequency",
          attrs: {
            type: "number",
            min: "0",
            step: "any",
            value: String(marker.frequencyHz),
            "aria-label": `Частота M${marker.id}, Гц`,
          },
        });
        frequency.hidden = marker.id !== selected;
        frequency.addEventListener("change", () => {
          const value = Number(frequency.value);
          if (frequency.value.trim() !== "" && Number.isFinite(value))
            view.moveMarker(marker.id, value);
        });
        const text = el("span", { text: formatHz(marker.frequencyHz) });
        text.hidden = marker.id === selected;
        const remove = el("button", {
          className: "lnt-sa-marker-remove",
          text: "×",
          attrs: {
            type: "button",
            "aria-label": `Удалить M${marker.id}`,
          },
        });
        remove.addEventListener("click", () => view.removeMarker(marker.id));
        return el("tr", { attrs: { "data-sa-marker": String(marker.id) } }, [
          el("td", { className: "lnt-sa-marker-tag" }, [select]),
          el("td", {}, [text, frequency]),
          el("td", { attrs: { "data-marker-level": "" }, text: formatDb(marker.levelDb) }),
          el("td", {}, [remove]),
        ]);
      }),
    );
    markerEmpty.hidden = list.length > 0;
    markerTable.hidden = list.length === 0;
    notice.hidden = true;
  }

  const tools = el("div", { className: "lnt-sa-marker-tools" }, [peakSearchButton, clearButton]);
  const view: SaMarkerPanelView = {
    root: el("section", { className: "panel lnt-sa-section lnt-sa-markers" }, [
      el("div", { className: "panel-hd" }, [
        el("h3", { className: "panel-title", text: "Маркеры и пики" }),
      ]),
      el("div", { className: "panel-bd" }, [
        tools,
        notice,
        markerEmpty,
        markerTable,
        peakEmpty,
        peakTable,
      ]),
    ]),
    tools,
    peakSearch: peakSearchButton,
    markersClear: clearButton,
    markerLines(): readonly SaMarkerLine[] {
      return markers.list().map((marker) => ({
        id: marker.id,
        frequencyHz: marker.frequencyHz,
        label: `M${marker.id}`,
        selected: marker.id === selected,
      }));
    },
    peakHighlight(): readonly ChartPeak[] {
      return highlight;
    },
    selectMarker(id): void {
      selected = id;
      applyMarkers();
      (deps.redraw ?? deps.rerender)();
    },
    moveMarker(id, frequencyHz): void {
      const freq = deps.store.freq();
      const clear = deps.store.trace("clear");
      markers.move(
        id,
        freq === null || clear === null ? null : { freq, psdDb: clear },
        frequencyHz,
      );
      selected = id;
      applyMarkers();
      (deps.redraw ?? deps.rerender)();
    },
    removeMarker(id): void {
      markers.remove(id);
      if (selected === id) selected = null;
      applyMarkers();
      (deps.redraw ?? deps.rerender)();
    },
    refreshFromStore(): void {
      const freq = deps.store.freq();
      const clear = deps.store.trace("clear");
      if (freq === null || clear === null) return;
      markers.refresh({ freq, psdDb: clear });
      for (const marker of markers.list()) {
        const level = markerBody.querySelector(
          `[data-sa-marker="${marker.id}"] [data-marker-level]`,
        );
        if (level !== null) level.textContent = formatDb(marker.levelDb);
      }
    },
    placeMarker(frequencyHz: number): void {
      const freq = deps.store.freq();
      const clear = deps.store.trace("clear");
      const trace = freq === null || clear === null ? null : { freq, psdDb: clear };
      const placement = markers.place(trace, frequencyHz);
      if (placement.kind === "rejected") {
        notice.textContent = REJECT_TEXT[placement.reason];
        notice.hidden = false;
        return;
      }
      applyMarkers();
      deps.rerender();
    },
  };
  return view;
}
