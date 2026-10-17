/** Хосты воркспейса «Спектроанализатор» для полосы (задача 12): инверсия
 * зависимости — полоса получает ГОТОВЫЕ узлы SA типизированным хэндлом,
 * а не селекторным поиском по DOM воркспейса. Имена — по SA-манифесту
 * полосы (span/rbw/run/traces/markers/peaks) плюс статус-строки и
 * обёртки leftover (гасятся классом после ре-парента их содержимого).
 * Ре-парент остаётся ответственностью полосы; воркспейс строит и отдаёт. */

import type { SaMarkerPanelView } from "./saMarkerPanel";
import type { SaStatusView } from "./saSections";
import type { SaConfigSelectors } from "./saSelectors";
import type { SaTraceControls } from "./saTraceControls";

export interface SaWorkspaceHosts {
  /** Корень воркспейса (.lnt-sa-workspace): полоса вешает класс режима. */
  readonly root: HTMLElement;
  readonly run: HTMLButtonElement;
  readonly stop: HTMLButtonElement;
  readonly bandLow: HTMLInputElement;
  readonly bandLowField: HTMLElement;
  readonly bandHigh: HTMLInputElement;
  readonly bandHighField: HTMLElement;
  readonly rbw: HTMLElement;
  readonly rbwField: HTMLElement;
  /** Ряд тумблеров трасс (.lnt-sa-trace-toggles). */
  readonly toggles: HTMLElement;
  /** «Сбросить статистику» (#lnt-sa-clear). */
  readonly traceClear: HTMLButtonElement;
  /** Инструментальный ряд маркеров/пиков (гасится после ре-парента). */
  readonly markerTools: HTMLElement;
  readonly markersClear: HTMLButtonElement;
  readonly peakSearch: HTMLButtonElement;
  readonly stateLine: HTMLElement;
  readonly simBadge: HTMLElement;
  readonly busyLine: HTMLElement;
  readonly errorHost: HTMLElement;
}

export interface SaWorkspaceHandle {
  readonly hosts: SaWorkspaceHosts;
  dispose(): void;
}

/** Сборка хостов из хэндлов секций: единственное место, знающее, какой
 * узел какой секции становится хостом полосы. */
export function saHostsFromViews(views: {
  root: HTMLElement;
  status: SaStatusView;
  selectors: SaConfigSelectors;
  traces: SaTraceControls;
  markers: SaMarkerPanelView;
}): SaWorkspaceHosts {
  const { status, selectors, traces, markers } = views;
  return {
    root: views.root,
    run: status.runButton,
    stop: status.stopButton,
    bandLow: selectors.bandLow,
    bandLowField: selectors.bandLowField,
    bandHigh: selectors.bandHigh,
    bandHighField: selectors.bandHighField,
    rbw: selectors.rbw,
    rbwField: selectors.rbwField,
    toggles: traces.toggles,
    traceClear: traces.clearButton,
    markerTools: markers.tools,
    markersClear: markers.markersClear,
    peakSearch: markers.peakSearch,
    stateLine: status.stateLine,
    simBadge: status.simBadge,
    busyLine: status.busyLine,
    errorHost: status.errorHost,
  };
}
