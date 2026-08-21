/** Под-клиент устройства и capture-preflight (routes_device.py).
 * Оба маршрута неинвазивные: POST /capture/preflight не требует nonce
 * (без require_csrf) и ничего не меняет в железе или задачах. */

import type { LntApiClient, RequestOptions } from "./client";
import { ApiError } from "./errors";
import { isDeviceStatePayload, isPreflightResponse } from "./guards-device";
import type { DeviceStatePayload, PreflightResponse } from "./types-device";
import type { CaptureJobRequest } from "./types-jobs";

export interface DeviceApi {
  /** GET /api/device/state — типизированное состояние без изменения устройства. */
  state(options?: RequestOptions): Promise<DeviceStatePayload>;
  /** POST /api/capture/preflight — отчёт безопасности до запуска job. */
  preflight(request: CaptureJobRequest, options?: RequestOptions): Promise<PreflightResponse>;
}

export function createDeviceApi(client: LntApiClient): DeviceApi {
  return {
    state: async (options = {}) => {
      const payload = await client.requestJson("GET", "/api/device/state", undefined, options);
      if (!isDeviceStatePayload(payload)) throw new ApiError("parse");
      return payload;
    },
    preflight: async (request, options = {}) => {
      const payload = await client.requestJson("POST", "/api/capture/preflight", request, options);
      if (!isPreflightResponse(payload)) throw new ApiError("parse");
      return payload;
    },
  };
}
