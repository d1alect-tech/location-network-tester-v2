/** Хосты воркспейса «Осциллограф» для полосы (задача 12): инверсия
 * зависимости — полоса получает ГОТОВЫЕ узлы продуктовых контролов
 * типизированным хэндлом, а не селекторным поиском по DOM воркспейса.
 * Имена — по манифесту полосы (scopeStripManifest: vdiv, probe, rate,
 * trigmode, trigsource, trigslope, level, cursors, history, measure,
 * persist) плюс run/stop, статус-строки и экран-хосты оверлеев.
 * Ре-парент остаётся ответственностью полосы (append в зоны);
 * воркспейс строит узлы и отдаёт их типом. */

import type { ScopeControlsView } from "./scopeControls";
import type { ScopeCursorView } from "./scopeCursorSection";
import type { MeasureRowState, ScopeMeasureView } from "./scopeMeasureConfig";
import type { ScopeRateField } from "./scopeRateField";
import type { ScopeScreenHandle } from "./scopeScreen";
import type { ScopeStatusView } from "./scopeSections";
import type { ScopeTriggerView } from "./scopeTrigger";

export interface ScopeWorkspaceHosts {
  /** Корень воркспейса (.lnt-scope-workspace): полоса вешает класс режима. */
  readonly root: HTMLElement;
  readonly run: HTMLButtonElement;
  readonly stop: HTMLButtonElement;
  readonly vdiv: HTMLElement;
  readonly probe: HTMLElement;
  readonly vdivEffective: HTMLElement;
  readonly rate: HTMLElement;
  readonly trigMode: HTMLElement;
  readonly trigSource: HTMLElement;
  readonly trigSlope: HTMLElement;
  readonly level: HTMLInputElement;
  /** Тумблер линий курсоров (#lnt-scope-cursors). */
  readonly cursors: HTMLElement;
  /** Секция курсоров: инлайн-ридаут, слайдеры, chart()/cursorsOn(). */
  readonly cursorsView: ScopeCursorView;
  readonly history: HTMLInputElement;
  readonly live: HTMLButtonElement;
  readonly screenNote: HTMLElement;
  readonly measure: HTMLElement;
  /** Ряды измерений (lnt.live.meas.v1): пресеты задач читают/пишут их
   *  живым API состояния (задача 17), не срезами DOM грида. */
  readonly measureRows: MeasureRowState;
  readonly persist: HTMLElement;
  readonly stateLine: HTMLElement;
  readonly simBadge: HTMLElement;
  readonly busyLine: HTMLElement;
  readonly errorHost: HTMLElement;
  readonly viewport: HTMLElement;
  readonly figure: HTMLElement;
}

export interface ScopeWorkspaceHandle {
  readonly hosts: ScopeWorkspaceHosts;
  dispose(): void;
}

/** Сборка хостов из хэндлов секций: единственное место, знающее, какой
 * узел какой секции становится хостом полосы. */
export function scopeHostsFromViews(views: {
  root: HTMLElement;
  status: ScopeStatusView;
  controls: ScopeControlsView;
  rateField: ScopeRateField;
  trigger: ScopeTriggerView;
  screen: ScopeScreenHandle;
  measure: ScopeMeasureView;
  measureRows: MeasureRowState;
  cursors: ScopeCursorView;
  figure: HTMLElement;
}): ScopeWorkspaceHosts {
  const { status, controls, rateField, trigger, screen, measure, measureRows, cursors } = views;
  return {
    root: views.root,
    run: status.runButton,
    stop: status.stopButton,
    vdiv: controls.vdiv,
    probe: controls.probe,
    vdivEffective: controls.vdivEffective,
    rate: rateField.root,
    trigMode: trigger.mode,
    trigSource: trigger.source,
    trigSlope: trigger.slope,
    level: trigger.level,
    cursors: cursors.toggle,
    cursorsView: cursors,
    history: screen.history,
    live: screen.live,
    screenNote: screen.screenNote,
    measure: measure.toggle,
    measureRows,
    persist: screen.persist,
    stateLine: status.stateLine,
    simBadge: status.simBadge,
    busyLine: status.busyLine,
    errorHost: status.errorHost,
    viewport: screen.viewport,
    figure: views.figure,
  };
}
