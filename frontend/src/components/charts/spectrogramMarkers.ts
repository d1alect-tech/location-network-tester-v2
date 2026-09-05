/** DOM-слой маркеров спектрограммы (C1-лист): геометрия кнопок-маркеров,
 * выбор/фокус/клавиатура — вынесены из spectrogramView.ts без изменения байтов.
 * Лист без обратного импорта вью: состояние перепозиции хранит последний
 * контекст (чарт/хост/домен), вью дёргает reposition после смены домена/тайла. */

import { el } from "../primitives/dom";
import type { SpectrogramChart } from "./echarts";

export interface MarkerSpec {
  timeS: number;
  label: string;
}

export interface MarkerLayerHandle {
  readonly element: HTMLElement;
  /** Перестроить кнопки по последнему контексту; контекст запоминается. */
  reposition(
    chart: SpectrogramChart | null,
    chartHost: HTMLElement,
    domainTimes: Float64Array<ArrayBufferLike>,
  ): void;
  /** Только состояние (сброс выбора); вью перепозиционирует следом. */
  setMarkers(value: readonly MarkerSpec[]): void;
  highlightMarker(index: number): void;
  focusMarker(index: number): boolean;
  onMarkerActivate(cb: (index: number) => void): void;
  /** Стрелки ←/→ на хосте канвы: фокус маркера + нотификация. */
  attachKeyboard(host: HTMLElement): void;
  dispose(): void;
}

export function createMarkerLayer(): MarkerLayerHandle {
  const element = el("div", {
    className: "lnt-spec-markers",
    attrs: { "aria-hidden": "true" },
  });
  let markers: readonly MarkerSpec[] = [];
  let selectedMarker = -1;
  const markerCallbacks: Array<(index: number) => void> = [];
  let lastChart: SpectrogramChart | null = null;
  let lastHost: HTMLElement | null = null;
  let lastTimes: Float64Array<ArrayBufferLike> = new Float64Array(0);

  function render(): void {
    element.replaceChildren();
    if (lastChart === null || lastChart.isDisposed() || markers.length === 0) return;
    const width = (lastHost as HTMLElement).clientWidth;
    for (const [index, marker] of markers.entries()) {
      let nearest = 0;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (let index2 = 0; index2 < lastTimes.length; index2 += 1) {
        const distance = Math.abs((lastTimes[index2] as number) - marker.timeS);
        if (distance < bestDistance) {
          bestDistance = distance;
          nearest = index2;
        }
      }
      const pixel = (lastChart as SpectrogramChart).convertToPixel({ xAxisIndex: 0 }, nearest);
      if (typeof pixel !== "number" || pixel < 0 || pixel > width) continue;
      const button = el("button", {
        className: index === selectedMarker ? "lnt-spec-marker is-selected" : "lnt-spec-marker",
        attrs: { type: "button", title: marker.label },
      });
      button.style.left = `${pixel}px`;
      button.addEventListener("click", () => {
        selectedMarker = index;
        render();
        for (const callback of markerCallbacks) callback(index);
      });
      element.append(button);
    }
  }

  function highlightMarker(index: number): void {
    selectedMarker = index;
    render();
    const buttons = element.querySelectorAll("button");
    buttons[index]?.classList.add("is-selected");
  }

  function focusMarker(index: number): boolean {
    const button = element.querySelectorAll("button")[index];
    if (button === undefined || button === null) return false;
    highlightMarker(index);
    button.focus();
    return true;
  }

  return {
    element,
    reposition(chart, chartHost, domainTimes) {
      lastChart = chart;
      lastHost = chartHost;
      lastTimes = domainTimes;
      render();
    },
    setMarkers(value) {
      markers = value;
      selectedMarker = -1;
    },
    highlightMarker(index) {
      highlightMarker(index);
    },
    focusMarker(index) {
      return focusMarker(index);
    },
    onMarkerActivate(cb) {
      markerCallbacks.push(cb);
    },
    attachKeyboard(host) {
      host.addEventListener("keydown", (event) => {
        if (markers.length === 0 || !(event instanceof KeyboardEvent)) return;
        let next = selectedMarker;
        if (event.key === "ArrowRight") next = Math.min(markers.length - 1, selectedMarker + 1);
        else if (event.key === "ArrowLeft") next = Math.max(0, selectedMarker - 1);
        else return;
        event.preventDefault();
        focusMarker(next);
        for (const callback of markerCallbacks) callback(next);
      });
    },
    dispose() {
      markerCallbacks.length = 0;
      markers = [];
    },
  };
}
