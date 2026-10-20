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
import { mountLivePresets } from "./livePresets";
import { mountScopeAutoset } from "./scopeAutoset";
import { buildBwFilterMenuSection } from "./scopeBwFilter";
import { mountScopeCaptureMenu } from "./scopeCaptureMenu";
import type { ScopeControlHosts } from "./scopeControlState";
import { applyScopeControlTargets, readScopeControlState } from "./scopeControlState";
import { mountScopeCursorDrag } from "./scopeCursorDrag";
import { mountScopeEdgeDrag } from "./scopeEdgeDrag";
import { mountScopeGroundLine } from "./scopeGroundLine";
import { buildMathTraceToggle } from "./scopeMathTrace";
import { mountScopeReset } from "./scopeReset";
import { VDIV_STEPS, windowHalfVolts } from "./scopeScale";
import { mountScopeStatus } from "./scopeStatus";
import { SCOPE_STRIP_ZONES } from "./scopeStripManifest";
import { TRIGGER_LEVEL_LIMIT_V } from "./scopeTrigger";
import { mountScopeTriggerLine } from "./scopeTriggerLine";
import { buildPersistenceMenuSection } from "./scopeWavePersistence";
import { findScopeWaveformView } from "./scopeWaveform";
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

  // Живые хосты контролов: читаются ДО монтажа экранной механики (окно
  // линии триггера и ручек нулевых линий живёт по staged-В/дел).
  const controlHosts: ScopeControlHosts = {
    vdiv: strip.groupHost("vdiv"),
    probe: strip.groupHost("probe"),
    rate: strip.groupHost("rate"),
    level: hosts.level,
    mode: strip.groupHost("trigmode"),
    source: strip.groupHost("trigsource"),
    slope: strip.groupHost("trigslope"),
  };

  /** Половина окна экрана по живым контролов: staged В/дел + пробник. */
  const liveWindowHalf = (): number => {
    const state = readScopeControlState(controlHosts);
    return windowHalfVolts(state.vdiv ?? VDIV_STEPS[0]!, state.probe ?? 1);
  };

  // Задача 15. Экран: линия триггера — DOM-оверлей, окно — ±4·В/дел
  // (директива 2026-10-19), синхронна полю и зоне ВЕРТ полосы.
  const triggerLine = mountScopeTriggerLine({
    viewport: hosts.viewport,
    field: hosts.level,
    live,
    windowHalfVolts: liveWindowHalf,
  });
  // Смена В/дел/пробника (клик в зоне ВЕРТ) переставляет линию триггера
  // и ручки нулевых линий под новое окно: слушатель в bubble-фазе читает
  // уже обновлённый живой DOM опций чипа/сегмента.
  for (const host of [strip.groupHost("vdiv"), strip.groupHost("probe")]) {
    host.addEventListener("click", () => {
      triggerLine.refresh();
      groundLine.repaint();
    });
  }

  // Задача 15. Фигура: drag курсорных линий — геометрия живого uPlot,
  // состояние тумблера; слайдеры — скрытый leftover с живыми слушателями.
  // Задача 19 (GATE A): edge-drag В/дел — кромка «экрана» (стекло + фигура
  // развёртки): арбитраж кромка > линия триггера > курсорные линии держит
  // capture-слушатель на hosts.root (списатели не правятся); В/дел пишется
  // тем же полем -> staged-грамматика наследуется, манифест не тронут.
  const edgeDrag = mountScopeEdgeDrag({
    host: hosts.root,
    surfaces: [hosts.viewport, hosts.figure],
    readVDiv: () => readScopeControlState(controlHosts).vdiv ?? VDIV_STEPS[0]!,
    writeVDiv: (value) => {
      applyScopeControlTargets(controlHosts, { vdiv: value });
    },
  });

  const cursorDrag = mountScopeCursorDrag({
    figure: hosts.figure,
    geometry: () => hosts.cursorsView.chart(),
    sliders: hosts.cursorsView.sliders,
    enabled: () => hosts.cursorsView.cursorsOn(),
  });

  // Директива владельца 2026-10-19: ручки нулевых линий каналов «1»/«2» —
  // drag на левой кромке фигуры развёртки, зажим в окно, сброс двойным
  // кликом; пишет через мост воркспейса (сдвиг ОТОБРАЖЕНИЯ, не измерений).
  const groundLine = mountScopeGroundLine({
    figure: hosts.viewport,
    read: () => hosts.ground.read(),
    write: (channel, volts) => hosts.ground.write(channel, volts),
    windowHalf: liveWindowHalf,
  });

  // Задача 15. ИЗМЕР: автосет (пересчёт по кадру + эхо + перезапуск) и
  // «Сброс» (дефолты манифеста) — живые слушатели листьев, эхо в статус-зоне.

  // Задача 16 (GATE A): тумблер математ-трассы CH1−CH2 в ИЗМЕР линии 2 —
  // третья серия стека развёртки (хэндл по фигуре, воркспейс не правится).
  const mathToggle = buildMathTraceToggle((on) => waveformView?.setMathMode(on));
  strip.groupHost("math").append(mathToggle.root);

  // Задача 17 (GATE A): пресеты задач — секция в меню захвата + stateless
  // диалог; хранение lnt.live.presets.v1, применение живыми слушателями
  // листьев (staged-грамматика полосы наследуется, мгновенного применения
  // старт-ручек нет). Хост — группа capture (якорь оверлея, тот же кластер).
  const presets = mountLivePresets({
    controls: controlHosts,
    measureRows: hosts.measureRows,
  });

  // Задача 24 (GATE A): секция «Полоса» в меню захвата — программный ФНЧ
  // отображения развёртки (клиентский, ярлык честности в секции и в [data-
  // wave-bw]); хэндл развёртки берётся по фигуре, воркспейс не правится.
  const waveformView = findScopeWaveformView(hosts.figure);
  const bwSection = buildBwFilterMenuSection({
    current: "full",
    onPick: (mode) => waveformView?.setBwFilter(mode),
  });
  // Задача 22: секция «Послесвечение» — режимы времени спада оверлея.
  const persistSection = buildPersistenceMenuSection({
    current: "off",
    onPick: (mode) => waveformView?.setPersistMode(mode),
  });
  // Задача 21 (GATE A): расширенное меню захвата — кнопка в ИЗМЕР, панель-
  // оверлей, пишет те же поля живыми слушателями листьев (staged-грамматика).
  const captureMenu = mountScopeCaptureMenu({
    host: strip.groupHost("capture"),
    controls: controlHosts,
    extras: el("div", {}, [bwSection, persistSection, presets.section]),
  });
  // Диалог пресетов встаёт в группу capture ПОСЛЕ кластера меню: первая
  // кнопка группы остаётся «Меню» (контракт scopeCaptureMenu).
  presets.attach(strip.groupHost("capture"));

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
    captureMenu.dispose();
    presets.dispose();
    edgeDrag.dispose();
    conflict.dispose();
    cursorDrag.dispose();
    groundLine.dispose();
    triggerLine.dispose();
    autoset.dispose();
    reset.dispose();
    status.dispose();
    cluster.dispose();
    strip.destroy();
    hosts.root.classList.remove("lnt-scope-strip-mode");
  };
}
