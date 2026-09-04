/** Устройство и preflight единого мок-бэкенда (только e2e/spec).
 * Тексты повторяют device_diagnostics.py; коды findings — контракты
 * routes_device.py / capture_preflight.py. Порядок findings зафиксирован:
 * device_not_ready первым (пин settings.spec), затем device_<state>. */

import type {
  DeviceStatePayload,
  DeviceStateValue,
  PreflightFinding,
  PreflightResponse,
} from "../api/types-device";

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
    description_ru: "Устройство не обнаружено на шине USB.",
    recovery_action_ru:
      "Подключите осциллограф и проверьте кабель; драйвер WinUSB ставится через Zadig (VID 04B4/04B5).",
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
    description_ru: "Устройство готово к захвату.",
    recovery_action_ru: "Дополнительные действия не требуются.",
  },
};

export function devicePayload(state: DeviceStateValue): DeviceStatePayload {
  return { state, ...DEVICE_TEXTS[state] };
}

/** Canned-preflight: блок device_not_ready + device_<state>, честные
 * трансформерные проверки line-quality, всегда warn о невыбранной базе. */
export function buildPreflight(
  deviceState: DeviceStateValue,
  body: Record<string, unknown>,
): PreflightResponse {
  const findings: PreflightFinding[] = [];
  if (deviceState !== "ready") {
    findings.push({
      severity: "block",
      code: "device_not_ready",
      message_ru: "Устройство не готово к записи.",
      recovery_action_ru: "Выполните действие из диагностики устройства.",
    });
    findings.push({
      severity: "block",
      code: `device_${deviceState}`,
      message_ru: `Устройство не готово: ${deviceState}.`,
      recovery_action_ru:
        "Выполните указанное диагностикой устройства действие и повторите preflight.",
    });
  }
  if (body.input === "transformer" && body.channels !== 1) {
    findings.push({
      severity: "block",
      code: "line_quality_requires_single_channel",
      message_ru: "Line-quality использует один трансформаторный канал CH1.",
      recovery_action_ru: "Выберите одноканальный режим; preflight не меняет его автоматически.",
    });
  }
  if (body.input === "transformer" && Number(body.range_v) < 5) {
    findings.push({
      severity: "warn",
      code: "line_quality_clipping_likely",
      message_ru: "Пик вторички около 16 В при пробнике 10x может перегрузить выбранный диапазон.",
      recovery_action_ru: "Выберите диапазон 5 В вручную; preflight не меняет настройку.",
    });
  }
  findings.push({
    severity: "warn",
    code: "baseline_not_requested",
    message_ru: "Самошум-базовая сессия не выбрана: приведение ко входу будет недоступно.",
    recovery_action_ru: "При необходимости снимите базовую сессию самошума в локации.",
  });
  return {
    ready: !findings.some((finding) => finding.severity === "block"),
    device_state: deviceState,
    findings,
  };
}
