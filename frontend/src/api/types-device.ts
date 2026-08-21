/** Доменные типы устройства и capture-preflight.
 * Источники: src/lnt/ui/routes_device.py, src/lnt/device_diagnostics.py,
 * src/lnt/capture_preflight.py. Имена полей совпадают с JSON бэкенда. */

/** DeviceState.value — стабильные состояния цепочки backend → USB → firmware. */
export const DEVICE_STATES = [
  "backend_unavailable",
  "driver_missing",
  "device_absent",
  "bootloader_vid",
  "running_vid",
  "handle_busy",
  "firmware_missing",
  "firmware_upload_failed",
  "ready",
] as const;
export type DeviceStateValue = (typeof DEVICE_STATES)[number];

/** Ответ GET /api/device/state. */
export interface DeviceStatePayload {
  state: DeviceStateValue;
  description_ru: string;
  recovery_action_ru: string;
}

/** PreflightFinding: severity block|warn, код, сообщение и ручное восстановление. */
export interface PreflightFinding {
  severity: "block" | "warn";
  code: string;
  message_ru: string;
  recovery_action_ru: string;
}

/** Ответ POST /api/capture/preflight. */
export interface PreflightResponse {
  ready: boolean;
  device_state: DeviceStateValue;
  findings: PreflightFinding[];
}
