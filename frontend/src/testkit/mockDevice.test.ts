/** TDD RED (очередь C2): устройство и preflight единого мока.
 * Пины: тексты recovery для Zadig-путей, порядок findings (device_not_ready
 * первым — пин settings.spec), трансформерные блокеры, baseline-warn. */

import { describe, expect, it } from "vitest";
import { DEVICE_TEXTS, buildPreflight } from "./mockDevice";

describe("единый мок: тексты устройства", () => {
  it("ready показывает действие из контракта, а не муляж", () => {
    expect(DEVICE_TEXTS.ready.description_ru).toContain("Устройство готово");
    expect(DEVICE_TEXTS.ready.recovery_action_ru).toContain("Дополнительные действия не требуются");
  });

  it("device_absent — штатное типизированное состояние с Zadig-действием", () => {
    expect(DEVICE_TEXTS.device_absent.description_ru).toContain(
      "Устройство не обнаружено на шине USB",
    );
    expect(DEVICE_TEXTS.device_absent.recovery_action_ru).toContain("Zadig");
  });

  it("driver_missing recovery ведёт через Zadig с VID", () => {
    expect(DEVICE_TEXTS.driver_missing.recovery_action_ru).toContain("Zadig");
    expect(DEVICE_TEXTS.driver_missing.recovery_action_ru).toContain("VID");
  });
});

describe("единый мок: preflight", () => {
  it("неготовое устройство: device_not_ready первым, затем device_<state>", () => {
    const response = buildPreflight("driver_missing", {});
    expect(response.ready).toBe(false);
    expect(response.device_state).toBe("driver_missing");
    expect(response.findings.length).toBeGreaterThanOrEqual(2);
    expect(response.findings[0]?.code).toBe("device_not_ready");
    expect(response.findings[1]?.code).toBe("device_driver_missing");
    expect(response.findings[0]?.severity).toBe("block");
  });

  it("готовое устройство: только предупреждение baseline, запуск разрешён", () => {
    const response = buildPreflight("ready", {});
    expect(response.ready).toBe(true);
    expect(response.findings.some((finding) => finding.severity === "block")).toBe(false);
    expect(response.findings[0]?.code).toBe("baseline_not_requested");
  });

  it("трансформерный вход с неверными каналами блокируется честным кодом", () => {
    const response = buildPreflight("ready", { input: "transformer", channels: 2, range_v: 5 });
    expect(response.ready).toBe(false);
    expect(
      response.findings.some((finding) => finding.code === "line_quality_requires_single_channel"),
    ).toBe(true);
  });

  it("трансформерный вход с малым диапазоном предупреждает о клиппинге", () => {
    const response = buildPreflight("ready", { input: "transformer", channels: 1, range_v: 1 });
    expect(response.ready).toBe(true);
    expect(
      response.findings.some((finding) => finding.code === "line_quality_clipping_likely"),
    ).toBe(true);
  });
});
