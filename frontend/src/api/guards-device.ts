/** Runtime-guards полезных нагрузок устройства и preflight (types-device). */

import { DEVICE_STATES } from "./types-device";
import type { DeviceStatePayload, PreflightFinding, PreflightResponse } from "./types-device";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isDeviceState(value: unknown): value is DeviceStatePayload["state"] {
  return typeof value === "string" && (DEVICE_STATES as readonly string[]).includes(value);
}

/** Проверяет ответ GET /api/device/state. */
export function isDeviceStatePayload(value: unknown): value is DeviceStatePayload {
  return (
    isRecord(value) &&
    isDeviceState(value.state) &&
    typeof value.description_ru === "string" &&
    typeof value.recovery_action_ru === "string"
  );
}

/** Проверяет один finding preflight: severity block|warn + русские тексты. */
export function isPreflightFinding(value: unknown): value is PreflightFinding {
  return (
    isRecord(value) &&
    (value.severity === "block" || value.severity === "warn") &&
    typeof value.code === "string" &&
    typeof value.message_ru === "string" &&
    typeof value.recovery_action_ru === "string"
  );
}

/** Проверяет ответ POST /api/capture/preflight. */
export function isPreflightResponse(value: unknown): value is PreflightResponse {
  return (
    isRecord(value) &&
    typeof value.ready === "boolean" &&
    isDeviceState(value.device_state) &&
    Array.isArray(value.findings) &&
    value.findings.every((item) => isPreflightFinding(item))
  );
}
