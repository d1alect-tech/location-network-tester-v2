/** Композиция scope-вкладки с полосой liveStrip (задача 14, зона-карта 13;
 * задача 12 — инверсия зависимости): полоса монтируется ПОСЛЕ воркспейса и
 * получает ГОТОВЫЕ узлы продуктовых контролов типизированным хэндлом
 * (ScopeWorkspaceHosts) — селекторного поиска по DOM воркспейса больше
 * нет, контракт узлов держат типы. Узлы переезжают в свои зоны append()-ом
 * (НЕ cloneNode: слушатели живы, программное управление идёт через них).
 * Ре-парент: сегменты В/дел/пробника + эффективное В/дел (zone-echo) в
 * ВЕРТ; чип частоты в ГОРИЗ; сегменты триггера в ТРИГГ (линия 1); степпер
 * вокруг живого поля #lnt-scope-level + индикатор тайминга в ТРИГГ (линия
 * 2); кнопки пуска в run-кластер ЗАПУСК; тумблер курсоров + ридаут Δt/ΔV,
 * слайдер истории/«Живой»/подпись кадров, кнопки автосета/сброса, ряд
 * измерений и тумблер послесвечения в ИЗМЕР; stateLine/simBadge/busyLine
 * и errorHost (absolute-оверлей) в статус-зону. Экран: линия триггера —
 * DOM-оверлей (±5 В), drag курсорных линий на фигуре, автосет/сброс через
 * живые слушатели (scopeControlState), эхо-строки в статус-зоне,
 * 409-клетка liveConflict на errorHost. Остаток панели ужимается классом
 * lnt-scope-strip-mode (сокрытие — НЕ удаление: модули живут и питаются
 * кадрами). Dispose отписывает всё от live-источника, затем снимает полосу. */

import { sharedLiveApi } from "../../api/client-live";
import type { LiveApi } from "../../api/client-live";
import {
  type LiveConflictSignal,
  mountLiveConflict,
} from "../../components/liveStrip/liveConflict";
import { mountLiveRunCluster } from "../../components/liveStrip/liveRunCluster";
import { wrapLiveStepper } from "../../components/liveStrip/liveStepper";
import { mountLiveStrip } from "../../components/liveStrip/liveStrip";
import { el } from "../../components/primitives/dom";
import { mountScopeAutoset } from "./scopeAutoset";
import type { ScopeControlHosts } from "./scopeControlState";
import { mountScopeCursorDrag } from "./scopeCursorDrag";
import { mountScopeReset } from "./scopeReset";
import { mountScopeStatus } from "./scopeStatus";
import { SCOPE_STRIP_ZONES } from "./scopeStripManifest";
import { TRIGGER_LEVEL_LIMIT_V } from "./scopeTrigger";
import { mountScopeTriggerLine } from "./scopeTriggerLine";
import type { ScopeWorkspaceHandle } from "./scopeWorkspaceHosts";

export interface ScopeStripOptions {
  /** Live-контур; по умолчанию — общий singleton, как у воркспейса. */
  live?: LiveApi;
  /** Сигнал 409 старта (обёртка signalLiveConflicts, проводит AppShell). */
  conflictSignal?: LiveConflictSignal;
  /** Хэндл смонтированного воркспейса: hosts — источник узлов для зон. */
  workspace: ScopeWorkspaceHandle;
}

export function mountScopeStrip(container: HTMLElement, options: ScopeStripOptions): () => void {
  const live = options.live ?? sharedLiveApi();
  const hosts = options.workspace.hosts;
  const strip = mountLiveStrip(SCOPE_STRIP_ZONES);
  container.append(strip.root);

  // ЗАПУСК: слитый кластер поверх живых кнопок пуска/останова.
  const cluster = mountLiveRunCluster({ run: hosts.run, stop: hosts.stop, live });
  strip.groupHost("run").append(cluster.root);

  // ВЕРТ: сегменты В/дел/пробника + эффективное В/дел (zone-echo, 0 px роста).
  hosts.vdivEffective.classList.add("lnt-live-echo");
  hosts.vdivEffective.setAttribute("data-readonly", "");
  strip.groupHost("vdiv").append(hosts.vdiv, hosts.vdivEffective);
  strip.groupHost("probe").append(hosts.probe);

  // ГОРИЗ: чип частоты (stateless listbox, note зоны — грамматика тайминга).
  strip.groupHost("rate").append(hosts.rate);

  // ТРИГГ, линия 1: живые сегменты режима/источника/фронта.
  strip.groupHost("trigmode").append(hosts.trigMode);
  strip.groupHost("trigsource").append(hosts.trigSource);
  strip.groupHost("trigslope").append(hosts.trigSlope);

  // ТРИГГ, линия 2: степпер вокруг живого поля уровня + индикатор тайминга.
  const stepper = wrapLiveStepper(hosts.level, {
    aria: "Уровень триггера",
    step: 0.1,
    min: -TRIGGER_LEVEL_LIMIT_V,
    max: TRIGGER_LEVEL_LIMIT_V,
    minusLabel: "Уменьшить уровень на 0,1 В",
    plusLabel: "Увеличить уровень на 0,1 В",
  });
  strip.groupHost("level").append(stepper.root);

  // ИЗМЕР: тумблер курсоров + инлайн-ридаут Δt/ΔV; история; измерения;
  // послесвечение (действия автосета/сброса — ниже, задача 15). Ридауты:
  // сетки НЕ переезжают в полосу (задача r5-9 W3) — измерения остаются в
  // рельсе воркспейса, курсорная сетка — скрытый leftover панели; полоса
  // несёт инлайн-строку Δt·ΔV (r4-грамматика).
  strip.groupHost("cursors").append(hosts.cursors, hosts.cursorsView.inlineReadout);
  strip.groupHost("history").append(hosts.history, hosts.live, hosts.screenNote);
  strip.groupHost("measure").append(hosts.measure);
  strip.groupHost("persist").append(hosts.persist);

  // Статус-зона: живые строки состояния + ошибки (absolute-оверлей).
  const statusZone = strip.statusZone();
  statusZone.append(hosts.stateLine, hosts.simBadge, hosts.busyLine, hosts.errorHost);

  const status = mountScopeStatus({
    live,
    hosts: {
      vdiv: strip.groupHost("vdiv"),
      probe: strip.groupHost("probe"),
      rate: strip.groupHost("rate"),
      trigMode: strip.groupHost("trigmode"),
      trigSource: strip.groupHost("trigsource"),
      trigSlope: strip.groupHost("trigslope"),
    },
    onPendingChange: (count) => cluster.setPendingCount(count),
  });
  strip.groupHost("trigState").append(status.trigState);
  statusZone.append(status.stagedLine);

  // Задача 15. Экран: линия триггера — DOM-оверлей ±5 В, синхронна полю.
  const triggerLine = mountScopeTriggerLine({
    viewport: hosts.viewport,
    field: hosts.level,
    live,
  });

  // Задача 15. Фигура: drag курсорных линий — геометрия живого uPlot,
  // состояние тумблера; слайдеры — скрытый leftover с живыми слушателями.
  const cursorDrag = mountScopeCursorDrag({
    figure: hosts.figure,
    geometry: () => hosts.cursorsView.chart(),
    sliders: hosts.cursorsView.sliders,
    enabled: () => hosts.cursorsView.cursorsOn(),
  });

  // Задача 15. ИЗМЕР: автосет (пересчёт по кадру + эхо + перезапуск) и
  // «Сброс» (дефолты манифеста) — живые слушатели листьев, эхо в статус-зоне.
  const controlHosts: ScopeControlHosts = {
    vdiv: strip.groupHost("vdiv"),
    probe: strip.groupHost("probe"),
    rate: strip.groupHost("rate"),
    level: hosts.level,
    mode: strip.groupHost("trigmode"),
    source: strip.groupHost("trigsource"),
    slope: strip.groupHost("trigslope"),
  };
  const echoSlot = (key: string): HTMLElement =>
    el("span", {
      className: "lnt-live-echo-line",
      attrs: { "data-echo": key, role: "status", hidden: "" },
    });
  const autosetEcho = echoSlot("autoset");
  const resetEcho = echoSlot("reset");
  statusZone.append(autosetEcho, resetEcho);
  const autoset = mountScopeAutoset({
    host: strip.groupHost("autoset"),
    hosts: controlHosts,
    live,
    restart: () => cluster.restart(),
    echo: autosetEcho,
  });
  const reset = mountScopeReset({
    host: strip.groupHost("reset"),
    hosts: controlHosts,
    echo: resetEcho,
  });

  // Задача 15. 409-клетка: конфликт живого захвата — баннер с переходом
  // на вкладку-конкурента (сигнал + текст-зеркало errorHost).
  const conflict = mountLiveConflict({
    errorHost: hosts.errorHost,
    otherRoute: "sa",
    otherTitle: "Спектроанализатор",
    stop: () => live.stop(),
    signal: options.conflictSignal,
  });

  // Компактный leftover: сокрытие хрома панелей, НЕ удаление модулей.
  hosts.root.classList.add("lnt-scope-strip-mode");

  return () => {
    conflict.dispose();
    cursorDrag.dispose();
    triggerLine.dispose();
    autoset.dispose();
    reset.dispose();
    status.dispose();
    cluster.dispose();
    strip.destroy();
    hosts.root.classList.remove("lnt-scope-strip-mode");
  };
}
