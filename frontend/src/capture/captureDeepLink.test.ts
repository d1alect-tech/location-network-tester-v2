import { describe, expect, it } from "vitest";
import { applyCapturePrefill, captureParamsToPrefill } from "./captureDeepLink";
import { createModeForm } from "./modeForm";

describe("captureParamsToPrefill (C1: билет из URL → предзаполнение формы)", () => {
  it("валидные параметры маппятся 1:1 в префилл формы", () => {
    // Given / When
    const prefill = captureParamsToPrefill({
      mode: "single_channel",
      source: "device",
      duration_s: "1.5",
      sample_rate_hz: "8000000",
      range_v: "1",
      label: "точка-7",
    });

    // Then
    expect(prefill).toEqual({
      modeId: "single_channel",
      source: "device",
      durationS: "1.5",
      sampleRateHz: "8000000",
      rangeV: "1",
      label: "точка-7",
    });
  });

  it("мусор в mode/source/range отбрасывается, честные поля живут", () => {
    // Given / When
    const prefill = captureParamsToPrefill({
      mode: "9ch",
      source: "эфир",
      range_v: "220",
      duration_s: "1.5",
    });

    // Then
    expect(prefill).toEqual({ durationS: "1.5" });
  });

  it("пустой query даёт пустой префилл (форма показывает свои дефолты)", () => {
    // Given / When
    const prefill = captureParamsToPrefill({ a: "x", b: "y" });

    // Then
    expect(prefill).toEqual({});
  });
});

describe("applyCapturePrefill (C1: префилл ложится в живую форму)", () => {
  it("режим/источник/числа/метка выставляются в DOM и уведомляют превью", () => {
    // Given
    const form = createModeForm();
    let notified = 0;
    form.onChange(() => {
      notified += 1;
    });

    // When
    applyCapturePrefill(form.root, {
      modeId: "single_channel",
      source: "device",
      durationS: "1.5",
      sampleRateHz: "8000000",
      rangeV: "1",
      label: "точка-7",
    });

    // Then
    expect(form.getMode().id).toBe("single_channel");
    expect(form.getSource()).toBe("device");
    expect(form.values()).toMatchObject({
      durationS: "1.5",
      sampleRateHz: "8000000",
      rangeV: "1",
      label: "точка-7",
    });
    expect(notified).toBeGreaterThan(0);
  });

  it("пустой префилл ничего не трогает (дефолты RC/симулятор на месте)", () => {
    // Given
    const form = createModeForm();

    // When
    applyCapturePrefill(form.root, {});

    // Then
    expect(form.getMode().id).toBe("rc_measurement");
    expect(form.getSource()).toBe("simulator");
    expect(form.values().durationS).toBe("2.4");
  });
});
