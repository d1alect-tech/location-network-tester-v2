/** Композиция scope-вкладки с полосой liveStrip (задача 14, зона-карта 13):
 * полоса монтируется ПОСЛЕ воркспейса (mountScopeWorkspace БЕЗ изменений) и
 * переезжает готовые DOM-узлы продуктовых контролов в свои зоны — append(),
 * НЕ cloneNode: слушатели живы, программное управление идёт через них.
 * Ре-парент: сегменты В/дел/пробника + эффективное В/дел (zone-echo) в ВЕРТ;
 * чип частоты в ГОРИЗ; сегменты триггера в ТРИГГ (линия 1); степпер вокруг
 * живого поля #lnt-scope-level + индикатор тайминга в ТРИГГ (линия 2);
 * кнопки пуска в run-кластер ЗАПУСК; слайдер истории/«Живой»/подпись кадров,
 * ряд измерений и тумблер послесвечения в ИЗМЕР; stateLine/simBadge/busyLine
 * и errorHost (absolute-оверлей) в статус-зону. Остаток панели ужимается
 * классом lnt-scope-strip-mode (сокрытие — НЕ удаление: модули живут и
 * питаются кадрами). Dispose отписывает статус и кластер от live-источника,
 * затем снимает полосу. */

import { sharedLiveApi } from "../../api/client-live";
import type { LiveApi } from "../../api/client-live";
import { mountLiveRunCluster } from "../../components/liveStrip/liveRunCluster";
import { wrapLiveStepper } from "../../components/liveStrip/liveStepper";
import { mountLiveStrip } from "../../components/liveStrip/liveStrip";
import { mountScopeStatus } from "./scopeStatus";
import { SCOPE_STRIP_ZONES } from "./scopeStripManifest";
import { TRIGGER_LEVEL_LIMIT_V } from "./scopeTrigger";

export interface ScopeStripOptions {
  /** Live-контур; по умолчанию — общий singleton, как у воркспейса. */
  live?: LiveApi;
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

  // ИЗМЕР: слайдер истории, «Живой», подпись кадров; измерения; послесвечение.
  move("#lnt-scope-history", "history");
  move("#lnt-scope-live", "history");
  move(".lnt-scope-screen-note", "history");
  move("#lnt-scope-measure", "measure");
  move(".lnt-scope-measure .readout-grid", "measure");
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

  // Компактный leftover: сокрытие хрома панелей, НЕ удаление модулей.
  workspace.classList.add("lnt-scope-strip-mode");

  return () => {
    status.dispose();
    cluster.dispose();
    strip.destroy();
    workspace.classList.remove("lnt-scope-strip-mode");
  };
}
