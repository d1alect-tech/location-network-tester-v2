import { describe, expect, it, vi } from "vitest";
import type { DeviceStatePayload } from "../../api/types-device";
import type { V6Chrome } from "./v6Chrome";
import { wireInspectDeviceStatus } from "./v6DeviceStatus";

function payload(): DeviceStatePayload {
  return {
    state: "ready",
    description_ru: "Устройство, WinUSB и RAM-прошивка готовы.",
    recovery_action_ru: "Дополнительные действия не требуются.",
  };
}

function chrome(): Pick<V6Chrome, "setDeviceStatus"> & { calls: unknown[][] } {
  const calls: unknown[][] = [];
  return {
    calls,
    setDeviceStatus: (...args: unknown[]) => {
      calls.push(args);
    },
  };
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("wireInspectDeviceStatus (C1: живой device-статус в командбаре)", () => {
  it("успешный GET /api/device/state отдаётся в командбар как есть", async () => {
    // Given
    const view = chrome();
    const source = { state: async () => payload() };

    // When
    wireInspectDeviceStatus(view, source);
    await flush();

    // Then
    expect(view.calls).toHaveLength(1);
    expect(view.calls[0]?.[0]).toEqual(payload());
  });

  it("обрыв запроса показывает честную ошибку, а не последнее известное состояние", async () => {
    // Given
    const view = chrome();
    const source = {
      state: async (): Promise<DeviceStatePayload> => {
        throw new Error("сервер не отвечает");
      },
    };

    // When
    wireInspectDeviceStatus(view, source);
    await flush();

    // Then
    expect(view.calls).toHaveLength(1);
    expect(view.calls[0]?.[0]).toBeNull();
    expect(view.calls[0]?.[1]).toContain("сервер не отвечает");
  });

  it("без источника показывает честное «нет данных», запроса нет", async () => {
    // Given
    const view = chrome();

    // When
    wireInspectDeviceStatus(view, undefined);
    await flush();

    // Then
    expect(view.calls).toHaveLength(1);
    expect(view.calls[0]?.[0]).toBeNull();
  });

  it("dispose до ответа гасит поздний результат (нет записи в отмонтированный хром)", async () => {
    // Given
    const view = chrome();
    let resolveState!: (value: DeviceStatePayload) => void;
    const source = {
      state: () =>
        new Promise<DeviceStatePayload>((resolve) => {
          resolveState = resolve;
        }),
    };
    const stop = vi.fn(wireInspectDeviceStatus(view, source));

    // When
    stop();
    resolveState(payload());
    await flush();

    // Then
    expect(stop).toHaveBeenCalledTimes(1);
    expect(view.calls).toHaveLength(0);
  });
});
