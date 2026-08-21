import type { Route } from "@playwright/test";
import type { DeviceStateValue } from "../api/types-device";
import type { JobSnapshot } from "../api/types-jobs";

/** Статические фикстуры мок-бэкенда: тексты device_diagnostics.py,
 * канонический payload JobSnapshot и сценарий задачи серии.
 * Все формы ответов повторяют контракты routes_jobs.py / routes_device.py. */

export const BUILD_ID = "build-t40";
export const NONCE = "nonce-t40";

export const DEVICE_TEXTS: Record<
  DeviceStateValue,
  { description_ru: string; recovery_action_ru: string }
> = {
  backend_unavailable: {
    description_ru: "Backend Hantek/libusb недоступен.",
    recovery_action_ru:
      "Установите extra lnt[hantek] и положите совместимую libusb-1.0.dll рядом с Python.",
  },
  driver_missing: {
    description_ru: "USB-устройство видно, но WinUSB для его VID не установлен.",
    recovery_action_ru:
      "Установите WinUSB через Zadig отдельно для обнаруженного VID и повторите проверку.",
  },
  device_absent: {
    description_ru: "Hantek DSO-6022BE не обнаружен на USB.",
    recovery_action_ru:
      "Подключите устройство и проверьте кабель/порт; переустановка backend не требуется.",
  },
  bootloader_vid: {
    description_ru: "Обнаружен загрузочный VID 04B4; рабочая RAM-прошивка ещё не активна.",
    recovery_action_ru:
      "Проверьте WinUSB для VID 04B4; прошивку загружайте только явной операцией захвата.",
  },
  running_vid: {
    description_ru: "Обнаружен рабочий VID 04B5, но готовность handle не подтверждена.",
    recovery_action_ru: "Закройте другие программы с осциллографом и повторите проверку.",
  },
  handle_busy: {
    description_ru: "USB-handle осциллографа занят другим процессом.",
    recovery_action_ru: "Закройте программу, удерживающую Hantek, и повторите проверку.",
  },
  firmware_missing: {
    description_ru: "Устройство открыто, но RAM-прошивка отсутствует.",
    recovery_action_ru: "Запустите захват явно: диагностика не загружает прошивку автоматически.",
  },
  firmware_upload_failed: {
    description_ru: "Предыдущая явная загрузка RAM-прошивки завершилась ошибкой.",
    recovery_action_ru:
      "Переподключите устройство, проверьте firmware-файлы и повторите явную операцию.",
  },
  ready: {
    description_ru: "Устройство, WinUSB и RAM-прошивка готовы.",
    recovery_action_ru: "Дополнительные действия не требуются.",
  },
};

/** Канонический снимок JobSnapshot.to_payload() с заменами поверх базы. */
export function snap(version: number, overrides: Partial<JobSnapshot>): JobSnapshot {
  return {
    schema_version: 1,
    version,
    job_id: "job-x",
    kind: "simulate",
    status: "queued",
    stage: "queued",
    series_index: null,
    series_total: null,
    written_sessions: [],
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

/** Тело SSE-потока с именованными событиями snapshot (routes_jobs.py). */
export function sseBody(events: JobSnapshot[]): string {
  let body = "retry: 150\n\n";
  for (const item of events) {
    body += `event: snapshot\nid: ${item.version}\ndata: ${JSON.stringify(item)}\n\n`;
  }
  return body;
}

export function json(payload: unknown, status = 200): Parameters<Route["fulfill"]>[0] {
  return { status, contentType: "application/json", body: JSON.stringify(payload) };
}

/** GET /api/config — единственный источник nonce запуска (ConfigPayload). */
export function configPayload() {
  return {
    root: "C:\\mock\\lnt-sessions",
    profiles: ["bad", "bad-damped", "quiet", "sync-only", "async-heavy"],
    defaults: {
      simulate: { duration_s: 2.4, sample_rate_hz: 500000, seed: 6022, repeat: 1, interval_s: 0 },
      capture: { duration_s: 2.4, sample_rate_hz: 8000000, range_v: 5, repeat: 1, interval_s: 0 },
      ranges: [5, 1, 0.5],
    },
    build_id: BUILD_ID,
    mutation_nonce: NONCE,
    static_asset_hash: "t40",
    static_assets: {},
  };
}

export interface JobScript {
  first: JobSnapshot;
  /** Первый рабочий снимок — отдаётся вместе с first автоматически. */
  runningSnap: JobSnapshot | undefined;
  scripted: JobSnapshot[];
}

/** Сценарий успешной задачи: queued → running(i1/N) [→ i2/N] → analyzing → done.
 * Имена записанных сессий индексируются сквозным счётчиком симуляции. */
export function buildJobScript(
  body: Record<string, unknown>,
  jobId: string,
  sessionNumber: number,
): JobScript {
  const kind = String(body.kind) as JobSnapshot["kind"];
  const repeat = Number(body.repeat ?? 1);
  const total = repeat > 1 ? repeat : null;
  const runStage = kind === "capture" ? "capturing" : "simulating";
  const prefix = kind === "capture" ? "cap" : "sim";
  const firstSession = `${prefix}-${String(sessionNumber).padStart(3, "0")}`;
  const sessions: string[] = [firstSession];
  let version = 1;
  const at = (overrides: Partial<JobSnapshot>): JobSnapshot => {
    version += 1;
    return snap(version, { job_id: jobId, kind, ...overrides });
  };
  const scripted: JobSnapshot[] = [
    at({
      status: "running",
      stage: runStage,
      series_index: total === null ? null : 1,
      series_total: total,
    }),
  ];
  if (total !== null) {
    scripted.push(
      at({
        status: "running",
        stage: runStage,
        series_index: 2,
        series_total: total,
        written_sessions: [...sessions],
      }),
    );
  }
  scripted.push(
    at({
      status: "succeeded",
      stage: "analyzing",
      series_index: total,
      series_total: total,
      written_sessions: [...sessions],
    }),
    at({
      status: "succeeded",
      stage: "done",
      series_index: total,
      series_total: total,
      written_sessions: [...sessions],
      result: { sessions },
    }),
  );
  const runningSnap = scripted.shift();
  return { first: snap(1, { job_id: jobId, kind }), runningSnap, scripted };
}
