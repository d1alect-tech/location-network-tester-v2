/** Композиция SA-вкладки с полосой liveStrip (задача 16, зона-карта 13;
 * задача 12 — инверсия зависимости): полоса монтируется ПОСЛЕ воркспейса
 * и получает ГОТОВЫЕ узлы SA типизированным хэндлом (SaWorkspaceHosts) —
 * селекторного поиска по DOM воркспейса больше нет. Узлы переезжают в
 * свои зоны append()-ом (НЕ cloneNode: слушатели живы, программное
 * управление идёт через них). Ре-парент: поля полосы в степперах и
 * RBW-сегменты (грамматика §2: дискрет ≤5 — инлайн-сегменты) в линии 1;
 * кнопки пуска в единый run-кластер ЗАПУСК (тот же liveRunCluster,
 * состояние из live-источника); тумблеры трасс + «Сбросить статистику»,
 * «Убрать маркеры», «Найти пики» в линии 2; stateLine/simBadge/busyLine
 * и errorHost (absolute-оверлей) в статус-зону. Опустевшие обёртки
 * leftover гасятся классом lnt-live-emptied (сокрытие, НЕ удаление).
 * saStatus — staged-реестр span/RBW при idle (маркеры + строка + бейдж);
 * 409-исход — liveConflict с переходом на вкладку «Осциллограф».
 * Рендер — общий стек saSpectrum (createUplotView), второй стек НЕ
 * заводится; SA-триггера нет — зеркало состояния сервиса (saWorkspace). */

import { sharedLiveApi } from "../../api/client-live";
import type { LiveApi } from "../../api/client-live";
import { DEFAULT_LIVE_START_REQUEST } from "../../api/types-live";
import {
  type LiveConflictSignal,
  mountLiveConflict,
} from "../../components/liveStrip/liveConflict";
import { mountLiveRunCluster } from "../../components/liveStrip/liveRunCluster";
import { wrapLiveStepper } from "../../components/liveStrip/liveStepper";
import { mountLiveStrip } from "../../components/liveStrip/liveStrip";
import type { LiveStripZoneDesc } from "../../components/liveStrip/liveStrip";
import { el } from "../../components/primitives/dom";
import { mountSaStatus } from "./saStatus";
import type { SaWorkspaceHandle } from "./saWorkspaceHosts";

/** Найквист дефолтного старта (8 МГц / 2) — потолок степпера полосы;
 * границу против реального захвата проверяет сервер (422). */
const SA_BAND_LIMIT_HZ = DEFAULT_LIVE_START_REQUEST.sample_rate_hz / 2;

/** Манифест зон SA-вкладки: 6 зон бенч-грамматики, набор ≠ scope.
 * Линия 1: ПОЛОСА (два поля со степперами), RBW (5 инлайн-сегментов),
 * ЗАПУСК (единый run-кластер). Линия 2: ТРАССЫ (4 тумблера + сброс
 * статистики — локальный склад), МАРКЕРЫ и ПИКИ (действия с исходом:
 * таблицы и подсветка остаются в main-области). */
export const SA_STRIP_ZONES: readonly LiveStripZoneDesc[] = [
  {
    zone: "span",
    label: "ПОЛОСА",
    aria: "Полоса частот",
    rows: [
      {
        line: 1,
        groups: [{ ctl: "span" }],
        note: "на ходу применяется сразу; без захвата — при запуске",
      },
    ],
  },
  {
    zone: "rbw",
    label: "RBW",
    aria: "Разрешающая полоса",
    rows: [{ line: 1, groups: [{ ctl: "rbw", label: "Гц" }] }],
  },
  {
    zone: "run",
    label: "ЗАПУСК",
    aria: "Запуск",
    rows: [{ line: 1, groups: [{ ctl: "run" }] }],
  },
  {
    zone: "traces",
    label: "ТРАССЫ",
    aria: "Трассы",
    rows: [{ line: 2, groups: [{ local: "traces" }] }],
  },
  {
    zone: "markers",
    label: "МАРКЕРЫ",
    aria: "Маркеры",
    rows: [{ line: 2, groups: [{ action: "markers" }] }],
  },
  {
    zone: "peaks",
    label: "ПИКИ",
    aria: "Поиск пиков",
    rows: [{ line: 2, groups: [{ action: "peaks" }] }],
  },
];

export interface SaStripOptions {
  /** Live-контур; по умолчанию — общий singleton, как у воркспейса. */
  live?: LiveApi;
  /** Сигнал 409 старта (обёртка signalLiveConflicts, проводит AppShell). */
  conflictSignal?: LiveConflictSignal;
  /** Хэндл смонтированного воркспейса: hosts — источник узлов для зон. */
  workspace: SaWorkspaceHandle;
}

export function mountSaStrip(container: HTMLElement, options: SaStripOptions): () => void {
  const live = options.live ?? sharedLiveApi();
  const hosts = options.workspace.hosts;
  const strip = mountLiveStrip(SA_STRIP_ZONES);
  container.append(strip.root);

  // Опустевшие обёртки leftover гасятся классом (сокрытие, НЕ удаление).
  const emptied = (node: HTMLElement): void => {
    node.classList.add("lnt-live-emptied");
  };

  // ЗАПУСК: единый run-кластер поверх живых кнопок пуска/останова.
  const cluster = mountLiveRunCluster({ run: hosts.run, stop: hosts.stop, live });
  strip.groupHost("run").append(cluster.root);

  // ПОЛОСА: два живых числовых поля в степперах (шаг 1 кГц, зажим Найквиста
  // дефолтного старта; поле — истина, запись — нативным change).
  const spanHost = strip.groupHost("span");
  for (const [field, fieldWrapper, aria, edge] of [
    [hosts.bandLow, hosts.bandLowField, "Начало полосы, Гц", "Начало"],
    [hosts.bandHigh, hosts.bandHighField, "Конец полосы, Гц", "Конец"],
  ] as const) {
    emptied(fieldWrapper);
    spanHost.append(
      el("span", { className: "lnt-live-ctl-label", text: edge }),
      wrapLiveStepper(field, {
        aria,
        step: 1000,
        min: 0,
        max: SA_BAND_LIMIT_HZ,
        stepBig: 100_000,
        minusLabel: `Уменьшить ${aria.toLowerCase()} на 1 кГц`,
        plusLabel: `Увеличить ${aria.toLowerCase()} на 1 кГц`,
      }).root,
    );
  }

  // RBW: 5 инлайн-сегментов (select заменён в saSelectors, живой слушатель).
  emptied(hosts.rbwField);
  strip.groupHost("rbw").append(hosts.rbw);

  // ТРАССЫ: тумблеры склада + «Сбросить статистику» (локальные, мгновенно).
  strip.groupHost("traces").append(hosts.toggles, hosts.traceClear);

  // МАРКЕРЫ / ПИКИ: действия с исходом (таблицы — в main-области).
  emptied(hosts.markerTools);
  strip.groupHost("markers").append(hosts.markersClear);
  strip.groupHost("peaks").append(hosts.peakSearch);

  // Статус-зона: живые строки состояния + ошибки (absolute-оверлей).
  const statusZone = strip.statusZone();
  statusZone.append(hosts.stateLine, hosts.simBadge, hosts.busyLine, hosts.errorHost);

  const status = mountSaStatus({
    live,
    hosts: { span: spanHost, rbw: strip.groupHost("rbw") },
    onPendingChange: (count) => cluster.setPendingCount(count),
  });
  statusZone.append(status.stagedLine);

  // 409-клетка: конфликт живого захвата — баннер с переходом на вкладку
  // «Осциллограф» (сигнал + текст-зеркало errorHost), Run не залипает.
  const conflict = mountLiveConflict({
    errorHost: hosts.errorHost,
    otherRoute: "scope",
    otherTitle: "Осциллограф",
    stop: () => live.stop(),
    signal: options.conflictSignal,
  });

  // Компактный leftover: сокрытие хрома панелей, НЕ удаление модулей.
  hosts.root.classList.add("lnt-sa-strip-mode");

  return () => {
    conflict.dispose();
    status.dispose();
    cluster.dispose();
    strip.destroy();
    hosts.root.classList.remove("lnt-sa-strip-mode");
  };
}
