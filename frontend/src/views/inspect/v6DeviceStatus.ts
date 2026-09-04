/** Живой device-статус командбара inspect (C1).
 * Один запрос GET /api/device/state при монтировании; результат —
 * в chrome.setDeviceStatus как есть (включая recovery_action_ru).
 * Без источника — честное «нет данных», обрыв — честная ошибка:
 * последнее известное состояние никогда не показывается как текущее. */

import type { DeviceStatePayload } from "../../api/types-device";
import type { V6Chrome } from "./v6Chrome";

export interface DeviceStatusSource {
  state(): Promise<DeviceStatePayload>;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

export function wireInspectDeviceStatus(
  chrome: Pick<V6Chrome, "setDeviceStatus">,
  source: DeviceStatusSource | undefined,
): () => void {
  let alive = true;
  if (source === undefined) {
    chrome.setDeviceStatus(null);
    return () => undefined;
  }
  void source.state().then(
    (payload) => {
      if (alive) chrome.setDeviceStatus(payload);
    },
    (error) => {
      if (alive) chrome.setDeviceStatus(null, errorText(error));
    },
  );
  return () => {
    alive = false;
  };
}
