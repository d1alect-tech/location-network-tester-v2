/** Реалистичный статический датасет витрин редизайна.
 *  Формы и значения взяты из реального домена LNT: каталог сессий,
 *  метрики анализа, пики спектра, режимы захвата, стадии задач, ошибки. */

export type ShowcaseHealth = "ok" | "partial" | "corrupt";

export interface ShowcaseSession {
  id: string;
  label: string;
  health: ShowcaseHealth;
  healthLabel: string;
  glyph: "●" | "▲" | "✕";
  typeLabel: string;
  date: string;
  storagePath?: string;
}

/** Краевая строка: метка 40+ символов, путь 120+ символов (проверка переполнения). */
const EDGE_STORAGE_PATH =
  "C:\\lnt-sessions\\архив-измерений\\2026\\август\\неделя-4\\локация-А-контрольная\\" +
  "щиток-1\\розетка-1\\замеры-после-ремонта-проводки\\повторная-серия-для-сравнения-с-базовой-записью\\" +
  "2026-08-25_08-15-33_rc";

export const SESSIONS: ShowcaseSession[] = [
  {
    id: "2026-08-29_14-30-00_rc",
    label: "стенд-А",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Захват",
    date: "2026-08-29",
  },
  {
    id: "2026-08-29_14-12-30_rc",
    label: "стенд-Б",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Захват",
    date: "2026-08-29",
  },
  {
    id: "2026-08-29_13-58-11_sn",
    label: "самошум",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Самошум",
    date: "2026-08-29",
  },
  {
    id: "2026-08-29_11-05-44_sim",
    label: "quiet",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Симуляция",
    date: "2026-08-29",
  },
  {
    id: "2026-08-28_22-41-09_lq",
    label: "кухня-трансформатор",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Качество сети",
    date: "2026-08-28",
  },
  {
    id: "2026-08-28_19-17-52_rc",
    label: "после-ремонта",
    health: "partial",
    healthLabel: "Частичная",
    glyph: "▲",
    typeLabel: "Захват",
    date: "2026-08-28",
  },
  {
    id: "2026-08-28_16-03-27_sim",
    label: "bad-damped",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Симуляция",
    date: "2026-08-28",
  },
  {
    id: "2026-08-27_09-44-15_rc",
    label: "подъезд-этаж-3",
    health: "corrupt",
    healthLabel: "Повреждён манифест",
    glyph: "✕",
    typeLabel: "Захват",
    date: "2026-08-27",
  },
  {
    id: "2026-08-26_21-30-00_rc",
    label: "серия-24ч",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Захват",
    date: "2026-08-26",
  },
  {
    id: "2026-08-25_08-15-33_rc",
    label: "длинная-метка-для-проверки-краевых-случаев",
    health: "ok",
    healthLabel: "Исправна",
    glyph: "●",
    typeLabel: "Захват",
    date: "2026-08-25",
    storagePath: EDGE_STORAGE_PATH,
  },
];

/** Числа из реального metrics.json (фикстура analysis-v2 measurement). */
export const METRICS = {
  lineFrequencyHz: 50.0000007,
  needleMeanV: 1.2904717,
  sigmaRatio: 6.217754,
  asyncSyncRatio: 73.286217,
  cyclesAnalyzed: 118,
  sampleRateHz: 100000,
  durationS: 2.4,
  bandLowHz: 3000,
  bandHighHz: 45000,
  resolutionHz: 97.65625,
};

export interface ShowcasePeak {
  frequencyHz: number;
  levelDb: number;
  prominenceDb: number;
  q: number;
}

export const PEAKS: ShowcasePeak[] = [
  { frequencyHz: 22418.2, levelDb: -48.57, prominenceDb: 26.5, q: 8.92 },
  { frequencyHz: 27439.8, levelDb: -49.95, prominenceDb: 27.08, q: 10.95 },
  { frequencyHz: 32456.7, levelDb: -50.95, prominenceDb: 26.87, q: 12.94 },
  { frequencyHz: 37471.7, levelDb: -51.65, prominenceDb: 26.06, q: 14.97 },
  { frequencyHz: 12329.0, levelDb: -43.93, prominenceDb: 24.52, q: 4.91 },
];

export interface ShowcaseCaptureMode {
  id: string;
  title: string;
  channels: string;
}

export const CAPTURE_MODES: ShowcaseCaptureMode[] = [
  { id: "rc_measurement", title: "RC-измерение (двухканальное)", channels: "2 (CH1 + CH2)" },
  { id: "self_noise", title: "Терминированный самошум", channels: "2 (CH1 + CH2)" },
  { id: "line_quality", title: "Качество сети (трансформатор 230:6)", channels: "1 (только CH1)" },
  { id: "single_channel", title: "Одноканальный захват", channels: "1 (только CH1)" },
];

export const CAPTURE_SOURCES = [
  { id: "simulator", title: "Симулятор", hint: "Синтетическая запись без железа." },
  {
    id: "device",
    title: "Осциллограф Hantek 6022BE",
    hint: "Реальная запись: требуется готовое устройство и пройденный preflight.",
  },
];

export const CAPTURE_FORM = {
  durationS: "2.4",
  sampleRateHz: "8000000",
  ranges: ["5 В", "1 В", "0,5 В"],
  profiles: ["bad", "bad-damped", "quiet", "sync-only", "async-heavy"],
  repeat: "1",
  intervalS: "0",
  label: "стенд-А",
};

export const JOB = {
  status: "Задача выполняется",
  stage: "захват",
  series: "Серия 2 из 5",
};

export const ERROR_STATE = {
  title: "Нет связи с сервером",
  message: "Нет связи с сервером. Проверьте, что панель запущена.",
  action: "Повторить подключение",
};

/** Форматирование частоты в русской нотации: 22418 Гц -> «22 418 Гц». */
export function formatHz(value: number): string {
  const rounded = Math.round(value);
  return `${new Intl.NumberFormat("ru-RU").format(rounded)} Гц`;
}
