/** Композиция scope-вкладки с полосой liveStrip (задача 14, зона-карта 13):
 * полоса монтируется ПОСЛЕ воркспейса (mountScopeWorkspace БЕЗ изменений) и
 * переезжает готовые DOM-узлы продуктовых контролов в свои зоны — append(),
 * НЕ cloneNode: слушатели живы, программное управление идёт через них.
 * Ре-парент: сегменты В/дел/пробника + эффективное В/дел (zone-echo) в ВЕРТ;
 * чип частоты в ГОРИЗ; сегменты триггера в ТРИГГ (линия 1); степпер вокруг
 * живого поля #lnt-scope-level + индикатор тайминга в ТРИГГ (линия 2);
 * кнопки пуска в run-кластер ЗАПУСК; тумблер курсоров + ридаут Δt/ΔV,
 * слайдер истории/«Живой»/подпись кадров, кнопки автосета/сброса, ряд
 * измерений и тумблер послесвечения в ИЗМЕР; stateLine/simBadge/busyLine
 * и errorHost (absolute-оверлей) в статус-зону. Задача 15: линия триггера
 * — DOM-оверлей на экране (±5 В), drag курсорных линий на фигуре,
 * автосет/сброс через живые слушатели (scopeControlState), эхо-строки
 * в статус-зоне, 409-клетка liveConflict на errorHost. Остаток панели
 * ужимается классом lnt-scope-strip-mode (сокрытие — НЕ удаление: модули
 * живут и питаются кадрами). Dispose отписывает всё от live-источника,
 * затем снимает полосу. */

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
import { findScopeCursorView } from "./scopeCursorSection";
import { mountScopeReset } from "./scopeReset";
import { mountScopeStatus } from "./scopeStatus";
import { SCOPE_STRIP_ZONES } from "./scopeStripManifest";
import { TRIGGER_LEVEL_LIMIT_V } from "./scopeTrigger";
import { mountScopeTriggerLine } from "./scopeTriggerLine";

export interface ScopeStripOptions {
  /** Live-контур; по умолчанию — общий singleton, как у воркспейса. */
  live?: LiveApi;
  /** Сигнал 409 старта (обёртка signalLiveConflicts, проводит AppShell). */
  conflictSignal?: LiveConflictSignal;
}

export function mountScopeStrip(
  container: HTMLElement,
  options: ScopeStripOptions = {},
): () => void {
  const live = options.live ?? sharedLiveApi();
  const workspace = container.querySelector<HTMLElement>(".lnt-scope-workspace");
  if (workspace === null) {
    throw new Error("mountScopeStrip: сначала монтируется воркспейс (mountScopeWorkspace)");
  }
  const strip = mountLiveStrip(SCOPE_STRIP_ZONES);
  container.append(strip.root);

  // ЗАПУСК: слитый кластер поверх живых кнопок пуска/останова.
  const run = workspace.querySelector<HTMLButtonElement>("#lnt-scope-run");
  const stop = workspace.querySelector<HTMLButtonElement>("#lnt-scope-stop");
  if (run === null || stop === null) {
    throw new Error("mountScopeStrip: нет кнопок пуска/останова");
  }
  const cluster = mountLiveRunCluster({ run, stop, live });
  strip.groupHost("run").append(cluster.root);

  // ВЕРТ: сегменты В/дел/пробника + эффективное В/дел (zone-echo, 0 px роста).
  const move = (selector: string, key: string): void => {
    const node = workspace.querySelector(selector);
    if (node === null) throw new Error(`mountScopeStrip: нет узла ${selector}`);
    strip.groupHost(key).append(node);
  };
  move("#lnt-scope-vdiv", "vdiv");
  move("#lnt-scope-probe", "probe");
  const effective = workspace.querySelector<HTMLElement>(".lnt-scope-vdiv-effective");
  if (effective !== null) {
    effective.classList.add("lnt-live-echo");
    effective.setAttribute("data-readonly", "");
    strip.groupHost("vdiv").append(effective);
  }

  // ГОРИЗ: чип частоты (stateless listbox, note зоны — грамматика тайминга).
  move(".lnt-scope-rate-field", "rate");

  // ТРИГГ, линия 1: живые сегменты режима/источника/фронта.
  for (const [key, attr] of [
    ["trigmode", "button[data-trigger-mode]"],
    ["trigsource", "button[data-trigger-source]"],
    ["trigslope", "button[data-trigger-slope]"],
  ] as const) {
    const button = workspace.querySelector(attr);
    const segRoot = button instanceof HTMLElement ? button.closest(".lnt-scope-seg") : null;
    if (segRoot === null) throw new Error(`mountScopeStrip: нет сегментов триггера (${key})`);
    strip.groupHost(key).append(segRoot);
  }

  // ТРИГГ, линия 2: степпер вокруг живого поля уровня + индикатор тайминга.
  const level = workspace.querySelector<HTMLInputElement>("#lnt-scope-level");
  if (level === null) throw new Error("mountScopeStrip: нет поля уровня");
  const stepper = wrapLiveStepper(level, {
    aria: "Уровень триггера",
    step: 0.1,
    min: -TRIGGER_LEVEL_LIMIT_V,
    max: TRIGGER_LEVEL_LIMIT_V,
    minusLabel: "Уменьшить уровень на 0,1 В",
    plusLabel: "Увеличить уровень на 0,1 В",
  });
  strip.groupHost("level").append(stepper.root);

  // ИЗМЕР: тумблер курсоров; история; измерения; послесвечение (действия
  // автосета/сброса — ниже, задача 15). Ридауты: сетки НЕ переезжают в полосу
  // (задача r5-9 W3) — измерения остаются в рельсе воркспейса, курсорная сетка
  // — скрытый leftover панели; полоса несёт инлайн-строку Δt·ΔV (r4-грамматика).
  move("#lnt-scope-cursors", "cursors");
  move("#lnt-scope-history", "history");
  move("#lnt-scope-live", "history");
  move(".lnt-scope-screen-note", "history");
  move("#lnt-scope-measure", "measure");
  move("#lnt-scope-persist", "persist");

  // Статус-зона: живые строки состояния + ошибки (absolute-оверлей).
  const statusZone = strip.statusZone();
  for (const selector of [".lnt-scope-state", ".lnt-scope-sim-badge", ".lnt-scope-busy"]) {
    const node = workspace.querySelector(selector);
    if (node !== null) statusZone.append(node);
  }
  const errorHost = workspace.querySelector<HTMLElement>(".lnt-scope-error-host");
  if (errorHost !== null) statusZone.append(errorHost);

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
  const viewport = workspace.querySelector<HTMLElement>(".lnt-scope-viewport");
  if (viewport === null) throw new Error("mountScopeStrip: нет экрана (viewport)");
  const triggerLine = mountScopeTriggerLine({ viewport, field: level, live });

  // Задача 15. Фигура: drag курсорных линий — геометрия живого uPlot,
  // состояние тумблера; слайдеры — скрытый leftover с живыми слушателями.
  const figure = workspace.querySelector<HTMLElement>(".lnt-scope-figure");
  const cursorsRoot = workspace.querySelector<HTMLElement>(".lnt-scope-cursors");
  if (figure === null || cursorsRoot === null) {
    throw new Error("mountScopeStrip: нет фигуры/секции курсоров");
  }
  const cursorView = findScopeCursorView(cursorsRoot);
  if (cursorView === undefined) {
    throw new Error("mountScopeStrip: нет хэндла секции курсоров");
  }
  strip.groupHost("cursors").append(cursorView.inlineReadout);
  const slider = (id: string): HTMLInputElement => {
    const node = workspace.querySelector<HTMLInputElement>(id);
    if (node === null) throw new Error(`mountScopeStrip: нет слайдера ${id}`);
    return node;
  };
  const cursorDrag = mountScopeCursorDrag({
    figure,
    geometry: () => findScopeCursorView(cursorsRoot)?.chart() ?? null,
    sliders: {
      t1: slider("#lnt-scope-cursor-t1"),
      t2: slider("#lnt-scope-cursor-t2"),
      v1: slider("#lnt-scope-cursor-v1"),
      v2: slider("#lnt-scope-cursor-v2"),
    },
    enabled: () => findScopeCursorView(cursorsRoot)?.cursorsOn() ?? false,
  });

  // Задача 15. ИЗМЕР: автосет (пересчёт по кадру + эхо + перезапуск) и
  // «Сброс» (дефолты манифеста) — живые слушатели листьев, эхо в статус-зоне.
  const controlHosts: ScopeControlHosts = {
    vdiv: strip.groupHost("vdiv"),
    probe: strip.groupHost("probe"),
    rate: strip.groupHost("rate"),
    level,
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
  const conflict =
    errorHost === null
      ? null
      : mountLiveConflict({
          errorHost,
          otherRoute: "sa",
          otherTitle: "Спектроанализатор",
          stop: () => live.stop(),
          signal: options.conflictSignal,
        });

  // Компактный leftover: сокрытие хрома панелей, НЕ удаление модулей.
  workspace.classList.add("lnt-scope-strip-mode");

  return () => {
    conflict?.dispose();
    cursorDrag.dispose();
    triggerLine.dispose();
    autoset.dispose();
    reset.dispose();
    status.dispose();
    cluster.dispose();
    strip.destroy();
    workspace.classList.remove("lnt-scope-strip-mode");
  };
}
