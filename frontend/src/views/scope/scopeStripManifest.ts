/** Манифест зон полосы вкладки «Осциллограф» (задача 14, зона-карта 13):
 * дескрипторы выбранного варианта V1 «Приборные клавиши» — 5 зон
 * бенч-грамматики в двух линиях виджетов. Линия 1: ВЕРТ (В/дел + пробник),
 * ГОРИЗ (чип частоты + note тайминга), ТРИГГ (режим/источник/фронт),
 * ЗАПУСК (слитый run-кластер). Линия 2: ИЗМЕР ведёт линию (история/
 * измерения/послесвечение), ТРИГГ продолжается правее (уровень-степпер +
 * индикатор тайминга). Курсоры и действия автосета/сброса добавляются
 * задачей 15 (семейство drag/действий) своими группами. Задача 15: ИЗМЕР
 * ведёт порядок cursors, history, autoset, reset, measure, persist
 * (квитанция задачи 5 §9d).
 * Задача 21 (GATE A 2026-10-18): манифест эволюционируется 12 → 13 контролов —
 * действие capture (зона ГОРИЗ, компактная кнопка) открывает overlay-меню
 * настройки захвата: пишет те же поля живыми слушателями листьев.
 * Размещение по геометрии: линия 2 на running растёт (живые значения
 * inline-ридаута Δt·ΔV), линия 1 стабильна — запас только в ГОРИЗ. */

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
        groups: [{ ctl: "rate" }, { action: "capture" }],
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
        groups: [
          { local: "cursors" },
          { local: "history" },
          { action: "autoset" },
          { action: "reset" },
          { local: "measure" },
          { local: "persist" },
        ],
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
