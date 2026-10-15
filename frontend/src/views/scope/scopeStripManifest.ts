/** Манифест зон полосы вкладки «Осциллограф» (задача 14, зона-карта 13):
 * дескрипторы выбранного варианта V1 «Приборные клавиши» — 5 зон
 * бенч-грамматики в двух линиях виджетов. Линия 1: ВЕРТ (В/дел + пробник),
 * ГОРИЗ (чип частоты + note тайминга), ТРИГГ (режим/источник/фронт),
 * ЗАПУСК (слитый run-кластер). Линия 2: ИЗМЕР ведёт линию (история/
 * измерения/послесвечение), ТРИГГ продолжается правее (уровень-степпер +
 * индикатор тайминга). Курсоры и действия автосета/сброса добавляются
 * задачей 15 (семейство drag/действий) своими группами. */

import type { LiveStripZoneDesc } from "../../components/liveStrip/liveStrip";

export const SCOPE_STRIP_ZONES: readonly LiveStripZoneDesc[] = [
  {
    zone: "vert",
    label: "ВЕРТ",
    aria: "Вертикаль",
    rows: [
      {
        line: 1,
        groups: [
          { ctl: "vdiv", label: "В/дел" },
          { ctl: "probe", label: "Пробник" },
        ],
      },
    ],
  },
  {
    zone: "horiz",
    label: "ГОРИЗ",
    aria: "Горизонталь",
    rows: [
      {
        line: 1,
        groups: [{ ctl: "rate" }],
        note: "применяется при запуске; на ходу не меняется",
      },
    ],
  },
  {
    zone: "measure",
    label: "ИЗМЕР",
    aria: "Измерения",
    rows: [
      {
        line: 2,
        groups: [{ local: "history" }, { local: "measure" }, { local: "persist" }],
      },
    ],
  },
  {
    zone: "trig",
    label: "ТРИГГ",
    aria: "Триггер",
    rows: [
      {
        line: 1,
        groups: [{ ctl: "trigmode" }, { ctl: "trigsource" }, { ctl: "trigslope" }],
      },
      {
        line: 2,
        groups: [{ ctl: "level" }, { slot: "trigState" }],
      },
    ],
  },
  {
    zone: "run",
    label: "ЗАПУСК",
    aria: "Запуск",
    rows: [{ line: 1, groups: [{ ctl: "run" }] }],
  },
];
