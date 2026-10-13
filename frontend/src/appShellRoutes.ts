/** Реестр маршрутов оболочки (выделен из AppShell, лимит 250 чистых LOC):
 * тип Route и таблица ROUTES — заголовки/описания разделов для анонса
 * навигации и заглушек-представлений. Только данные, без DOM. */

export type Route =
  | "catalog"
  | "capture"
  | "scope"
  | "sa"
  | "inspect"
  | "experiments"
  | "reports"
  | "settings";

export const ROUTES: Record<Route, { title: string; desc: string }> = {
  capture: {
    title: "Захват",
    desc: "Запуск одиночных или серийных измерений, отображение активной задачи.",
  },
  // BEGIN Todo 7: приборные вкладки (группа live-маршрутов {scope, sa}).
  scope: {
    title: "Осциллограф",
    desc: "Живой режим развёртки: непрерывный поток кадров, Run/Stop и статус владения прибором.",
  },
  // BEGIN Todo 14: приборная вкладка «Спектроанализатор» (группа live-маршрутов).
  sa: {
    title: "Спектроанализатор",
    desc: "Живые трассы спектра: clear-write, min/max-hold и бегущее среднее; полоса и RBW на ходу.",
  },
  // END Todo 14
  // END Todo 7
  inspect: {
    title: "Инспекция",
    desc: "Детальный анализ выбранной сессии, просмотр спектра мощности (PSD).",
  },
  experiments: {
    title: "Эксперименты",
    desc: "Группировка сессий по протоколам (A/B, A/B/A, повторные серии).",
  },
  reports: {
    title: "Отчёты",
    desc: "Генерация научных отчетов с полной прослеживаемостью (provenance).",
  },
  settings: {
    title: "Настройки",
    desc: "Управление путями сессий, базами данных, резервным копированием.",
  },
  // ===== BEGIN T39 CATALOG REGISTRATION (todo 39) =====
  catalog: {
    title: "Каталог",
    desc: "Поиск и фильтрация сессий, инспектор контекста, управление профилями.",
  },
  // ===== END T39 CATALOG REGISTRATION =====
};
