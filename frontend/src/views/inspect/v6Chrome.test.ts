import { describe, expect, it, vi } from "vitest";
import { createV6Chrome } from "./v6Chrome";

describe("createV6Chrome", () => {
  it("exposes a capture-form commandbar whose submit button calls onCapture once", () => {
    // Given
    const onCapture = vi.fn();
    const { commandbar } = createV6Chrome({ onCapture });

    // When
    const submit = commandbar.querySelector("button[type=submit]");
    expect(commandbar.getAttribute("data-showcase")).toBe("capture-form");
    expect(submit).toBeInstanceOf(HTMLButtonElement);
    if (!(submit instanceof HTMLButtonElement)) return;
    submit.click();

    // Then
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it("submit передаёт значения формы билетом (режим/источник/длительность/частота/диапазон/метка)", () => {
    // Given
    const seen: unknown[] = [];
    const { commandbar } = createV6Chrome({ onCapture: (ticket) => seen.push(ticket) });
    const form = commandbar as HTMLFormElement;
    document.body.append(form);
    try {
      (form.querySelector('select[name="mode"]') as HTMLSelectElement).value = "1ch";
      (form.querySelector('select[name="source"]') as HTMLSelectElement).value = "device";
      (form.querySelector('input[name="duration"]') as HTMLInputElement).value = "1.5";
      (form.querySelector('input[name="rate"]') as HTMLInputElement).value = "8000000";
      (form.querySelector('select[name="range"]') as HTMLSelectElement).value = "5v";
      (form.querySelector('input[name="label"]') as HTMLInputElement).value = "точка-7";

      // When: submit формы (Enter в поле — неявная отправка, как в браузере)
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

      // Then: ввод не выбрасывается — едет билетом в capture
      expect(seen).toEqual([
        {
          mode: "1ch",
          source: "device",
          duration: "1.5",
          rate: "8000000",
          range: "5v",
          label: "точка-7",
        },
      ]);
    } finally {
      form.remove();
    }
  });

  it("device-статус: ready — ок-пилюля с действием из бэкенда", () => {
    // Given
    const { commandbar, setDeviceStatus } = createV6Chrome({ onCapture: () => undefined });

    // When
    setDeviceStatus({
      state: "ready",
      description_ru: "Устройство, WinUSB и RAM-прошивка готовы.",
      recovery_action_ru: "Дополнительные действия не требуются.",
    });

    // Then
    const status = commandbar.querySelector("[data-device-status]");
    expect(status?.textContent).toContain("Устройство готово");
    expect(status?.textContent).toContain("Дополнительные действия не требуются.");
  });

  it("device-статус: неготовность и обрыв — честные тексты, а не тишина", () => {
    // Given
    const { commandbar, setDeviceStatus } = createV6Chrome({ onCapture: () => undefined });
    const status = () => commandbar.querySelector("[data-device-status]")?.textContent ?? "";

    // When: драйвер missing с действием Zadig
    setDeviceStatus({
      state: "driver_missing",
      description_ru: "USB-устройство видно, но WinUSB для его VID не установлен.",
      recovery_action_ru: "Установите WinUSB через Zadig.",
    });
    expect(status()).toContain("Устройство не готово");
    expect(status()).toContain("Установите WinUSB через Zadig.");

    // When: обрыв связи
    setDeviceStatus(null, "сервер не отвечает");
    expect(status()).toContain("Устройство недоступно");
    expect(status()).toContain("сервер не отвечает");

    // When: источника нет вообще
    setDeviceStatus(null);
    expect(status()).toContain("нет данных");
  });

  it("hides the error band until showError and hides it again on hideError", () => {
    // Given
    const { errorBand, showError, hideError } = createV6Chrome({
      onCapture: () => undefined,
    });
    expect(errorBand.hidden).toBe(true);

    // When
    showError("нет сессии");

    // Then
    expect(errorBand.hidden).toBe(false);
    expect(errorBand.textContent).toBe("нет сессии");

    hideError();
    expect(errorBand.hidden).toBe(true);
  });
});
