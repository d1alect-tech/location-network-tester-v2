/** Живые приборные вкладки «Осциллограф»/«Спектроанализатор» (задача 16,
 * сплит AppShell по зоне-карте §4 «views/liveTabs.ts при >250»): монтаж
 * воркспейса + полосы liveStrip с инструментированным live-контуром —
 * 409 старта уходит сигналом liveConflict (баннер с переходом), воркспейсы
 * без правок. Полоса монтируется ПОСЛЕ воркспейса и ре-парентит живые
 * узлы контролов; dispose-цепочка отписывает полосу первой. Маршрутный
 * хром (очистка контейнера, классы вида) остаётся в AppShell. */

import type { LntApiClient } from "../api/client";
import { sharedLiveApi } from "../api/client-live";
import {
  createLiveConflictSignal,
  signalLiveConflicts,
} from "../components/liveStrip/liveConflict";
import { mountSaStrip } from "./sa/saStrip";
import { mountSaWorkspace } from "./sa/saWorkspace";
import { mountScopeStrip } from "./scope/scopeStrip";
import { mountScopeWorkspace } from "./scope/scopeWorkspace";

export function mountScopeTab(container: HTMLElement, client: LntApiClient): () => void {
  const conflictSignal = createLiveConflictSignal();
  const live = signalLiveConflicts(sharedLiveApi(), conflictSignal);
  const workspace = mountScopeWorkspace(container, { client, live });
  const disposeStrip = mountScopeStrip(container, { live, conflictSignal, workspace });
  return () => {
    disposeStrip();
    workspace.dispose();
  };
}

export function mountSaTab(container: HTMLElement, client: LntApiClient): () => void {
  const conflictSignal = createLiveConflictSignal();
  const live = signalLiveConflicts(sharedLiveApi(), conflictSignal);
  const workspace = mountSaWorkspace(container, { client, live });
  const disposeStrip = mountSaStrip(container, { live, conflictSignal, workspace });
  return () => {
    disposeStrip();
    workspace.dispose();
  };
}
