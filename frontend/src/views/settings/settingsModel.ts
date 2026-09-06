/** Чистая модель «Настроек» (#/settings): сводка приватности, зеркалящая
 * семантику lnt/metadata_collector.py (todo 8), инструкция сборника
 * поддержки (кнопки панели запускают задачи backup/support_bundle через
 * POST /api/jobs; CLI lnt support-bundle остаётся доступным) и валидация
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
  /** Панель запускает сборку задачами backup/support_bundle (POST /api/jobs). */
  httpAvailable: boolean;
  command: string;
  flags: { flag: string; detail: string }[];
  contents: string[];
  manifestNote: string;
}

/** Инструкция: сборка кнопками панели; CLI-команда остаётся запасным путём. */
export function supportBundleGuidance(): SupportBundleGuidance {
  return {
    httpAvailable: true,
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

/** Вид задачи сборки: полный бэкап корня или сборник поддержки. */
export type BundleJobKind = "backup" | "support_bundle";

/** Имя выходного файла из result терминального снимка (ключи path/file/archive/bundle). */
export function bundleFile(result: Record<string, unknown> | null): string | null {
  const value = result?.path ?? result?.file ?? result?.archive ?? result?.bundle;
  return typeof value === "string" && value !== "" ? value : null;
}

/** Русские тексты статуса задачи сборки (запуск / успех / провал). */
export function bundleRunning(kind: BundleJobKind): string {
  return kind === "backup" ? "Создание бэкапа…" : "Сборка сборника поддержки…";
}

export function bundleDone(kind: BundleJobKind, file: string | null): string {
  const head = kind === "backup" ? "Бэкап создан" : "Сборник поддержки собран";
  return file === null ? `${head}.` : `${head}: ${file}`;
}

export function bundleFailed(kind: BundleJobKind, reason: string): string {
  const head = kind === "backup" ? "Не удалось создать бэкап" : "Не удалось собрать сборник";
  return `${head}: ${reason}`;
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

/** Папка сессий: те же правила длины и запрещённых символов, что у
 * validateRootNote, плюс обязательный абсолютный путь Windows (буква диска
 * `X:\` или UNC `\\`). Пустая строка не проходит: папку надо указать явно.
 * Проверяется только форма записи; есть ли папка на диске, станет ясно при
 * следующем старте сервера. */
export function validateSessionsFolder(value: string): RootNoteValidation {
  const trimmed = value.trim();
  if (trimmed.length === 0) return { ok: false, error: "Укажите путь к папке сессий." };
  if (trimmed.length > ROOT_NOTE_MAX_LENGTH) {
    return { ok: false, error: `Максимум ${ROOT_NOTE_MAX_LENGTH} символов.` };
  }
  if (/[\n\r]/.test(trimmed)) {
    return { ok: false, error: "Путь должен быть одной строкой." };
  }
  if (/[<>|?*"]/.test(trimmed)) {
    return { ok: false, error: "Путь содержит недопустимые символы." };
  }
  if (!/^[A-Za-z]:\\/.test(trimmed) && !/^\\\\/.test(trimmed)) {
    return {
      ok: false,
      error: "Нужен абсолютный путь Windows: D:\\lnt-sessions или \\\\server\\share.",
    };
  }
  return { ok: true, error: null };
}
