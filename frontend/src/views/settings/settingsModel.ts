/** Чистая модель «Настроек» (#/settings): сводка приватности, зеркалящая
 * семантику lnt/metadata_collector.py (todo 8), честная инструкция сборника
 * поддержки (HTTP-маршрута нет — только CLI lnt support-bundle) и валидация
 * локальной заметки о корне сессий. Никаких выдуманных эндпоинтов. */

export interface PrivacyItem {
  /** Ключ поля как в metadata snapshot (например device.vid). */
  key: string;
  detail: string;
}

export interface PrivacyGroup {
  id: "automatic" | "opt_in" | "never";
  title: string;
  intro: string;
  items: PrivacyItem[];
}

/** Группы приватности: собрано автоматически / только явный выбор / никогда. */
export function privacyGroups(): PrivacyGroup[] {
  return [
    {
      id: "automatic",
      title: "Собирается автоматически",
      intro:
        "Эти поля попадают в метаданные каждой сессии (metadata snapshot, schema 1). Недоступное поле записывается с кодом причины, а не выдуманным значением.",
      items: [
        { key: "lnt.version / lnt.build / lnt.mode", detail: "версия, сборка и режим приложения" },
        {
          key: "os.version / os.architecture / os.timezone",
          detail: "разрешённая информация об ОС",
        },
        {
          key: "device.vid / pid / model / firmware / driver",
          detail: "ограниченная диагностика устройства; при недоступности — reason_code",
        },
        { key: "sample.rate_hz / sample.count", detail: "параметры записи" },
        { key: "probe.multiplier / range.v / channel.mode", detail: "настройки входа" },
        { key: "front_end.resistance_ohm / c1_f / c2_f", detail: "параметры ВЧ-фронтенда" },
        {
          key: "acquisition.*",
          detail:
            "телеметрия захвата: счётчики сэмплов, колбэков, коротких блоков, клиппинга, calibration_used",
        },
      ],
    },
    {
      id: "opt_in",
      title: "Только явный выбор (opt-in)",
      intro: "В сборник поддержки эти члены попадают только если вы явно попросили.",
      items: [
        {
          key: "приватные заметки",
          detail: "по умолчанию выключены (--include-private-notes включает)",
        },
        {
          key: "хвост журнала",
          detail: "последние строки журнала; по умолчанию включены, отключается --no-logs",
        },
      ],
    },
    {
      id: "never",
      title: "Никогда не собирается",
      intro: "Гарантии privacy-bounded сбора.",
      items: [
        { key: "сырые захваты", detail: "ch1.npy/ch2.npy не включаются в диагностику никогда" },
        {
          key: "значения конфигурации",
          detail: "в сборник поддержки уходит только версия схемы: пути и токены не выгружаются",
        },
        {
          key: "сетевая телеметрия",
          detail: "панель работает офлайн: сервер слушает только 127.0.0.1, внешних запросов нет",
        },
      ],
    },
  ];
}

export interface SupportBundleGuidance {
  /** HTTP-маршрут отсутствует: кнопки сборки в панели НЕТ и не будет,
   * пока бэкенд его не предоставит. */
  httpAvailable: false;
  command: string;
  flags: { flag: string; detail: string }[];
  contents: string[];
  manifestNote: string;
}

/** Честная инструкция: сборник поддержки собирается CLI-командой. */
export function supportBundleGuidance(): SupportBundleGuidance {
  return {
    httpAvailable: false,
    command: "uv run lnt support-bundle <путь\\к\\lnt-support.zip>",
    flags: [
      {
        flag: "--include-private-notes",
        detail: "включить приватные заметки (по умолчанию выключены)",
      },
      { flag: "--no-logs", detail: "не включать хвост журнала (по умолчанию включён)" },
    ],
    contents: [
      "config.json — только версия схемы конфигурации",
      "device.json — состояние устройства без строк драйвера с путями машины",
      "build.json — идентичность кода, версия Python, платформа",
      "dependencies.json — имя/версия зависимостей",
      "logs/recent.jsonl — хвост журнала (если не отключён)",
    ],
    manifestNote:
      "manifest.json фиксирует состав и SHA-256 каждого члена: получатель может проверить целостность.",
  };
}

export const ROOT_NOTE_MAX_LENGTH = 200;

export interface RootNoteValidation {
  ok: boolean;
  error: string | null;
}

/** Локальная заметка о желаемом корне: подсказка оператору, НЕ серверная
 * настройка. Фактический корень отдаёт GET /api/config и меняется только
 * перезапуском сервера с --root. */
export function validateRootNote(value: string): RootNoteValidation {
  const trimmed = value.trim();
  if (trimmed.length === 0) return { ok: true, error: null };
  if (trimmed.length > ROOT_NOTE_MAX_LENGTH) {
    return { ok: false, error: `Максимум ${ROOT_NOTE_MAX_LENGTH} символов.` };
  }
  if (/[\n\r]/.test(trimmed)) {
    return { ok: false, error: "Путь должен быть одной строкой." };
  }
  if (/[<>|?*"]/.test(trimmed)) {
    return { ok: false, error: "Путь содержит недопустимые символы." };
  }
  return { ok: true, error: null };
}
