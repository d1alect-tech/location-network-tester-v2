import { describe, expect, it, vi } from "vitest";
import type { LntApiClient } from "./client";
import { createDeviceApi } from "./client-device";
import type { ApiError } from "./errors";

function fakeClient(
  response: unknown,
  ok = true,
): { client: LntApiClient; spy: ReturnType<typeof vi.fn> } {
  const spy = vi.fn(async () => {
    if (!ok) throw new Response();
    return response;
  });
  return {
    client: {
      requestJson: spy as unknown as LntApiClient["requestJson"],
    } as unknown as LntApiClient,
    spy,
  };
}

const statePayload = {
  state: "driver_missing",
  description_ru: "USB-устройство видно, но WinUSB для его VID не установлен.",
  recovery_action_ru:
    "Установите WinUSB через Zadig отдельно для обнаруженного VID и повторите проверку.",
};

const preflightPayload = {
  ready: false,
  device_state: "handle_busy",
  findings: [
    {
      severity: "block",
      code: "device_handle_busy",
      message_ru: "Устройство не готово: handle_busy.",
      recovery_action_ru:
        "Выполните указанное диагностикой устройства действие и повторите preflight.",
    },
  ],
};

describe("device api client", () => {
  it("GET /api/device/state returns a guarded payload", async () => {
    const { client, spy } = fakeClient(statePayload);
    const device = createDeviceApi(client);
    const payload = await device.state();
    expect(spy).toHaveBeenCalledWith("GET", "/api/device/state", undefined, {});
    expect(payload.state).toBe("driver_missing");
  });

  it("POST /api/capture/preflight passes the capture contract body", async () => {
    const { client, spy } = fakeClient(preflightPayload);
    const device = createDeviceApi(client);
    const payload = await device.preflight({
      kind: "capture",
      duration_s: 2.4,
      sample_rate_hz: 8_000_000,
      range_v: 5,
      self_noise: false,
      baseline_session: null,
      channels: 1,
      input: "transformer",
      repeat: 1,
      interval_s: 0,
    });
    expect(spy).toHaveBeenCalledWith(
      "POST",
      "/api/capture/preflight",
      expect.objectContaining({ kind: "capture" }),
      {},
    );
    expect(payload.ready).toBe(false);
    expect(payload.findings[0]?.code).toBe("device_handle_busy");
  });

  it("throws ApiError(parse) on shape drift instead of leaking bad data", async () => {
    const { client } = fakeClient({ state: "unknown_state" });
    const device = createDeviceApi(client);
    await expect(device.state()).rejects.toMatchObject({
      kind: "parse",
    } satisfies Partial<ApiError>);
  });
});
