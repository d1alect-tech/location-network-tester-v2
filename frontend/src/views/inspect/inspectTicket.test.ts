import { describe, expect, it } from "vitest";
import { ticketToCaptureParams } from "./inspectTicket";
import type { InspectCaptureTicket } from "./v6Chrome";

function ticket(overrides: Partial<InspectCaptureTicket> = {}): InspectCaptureTicket {
  return {
    mode: "2ch",
    source: "sim",
    duration: "2.4",
    rate: "8000000",
    range: "5v",
    label: "",
    ...overrides,
  };
}

describe("ticketToCaptureParams (C1: командбар inspect → билет в capture)", () => {
  it("маппит сырой билет командбара в нативные параметры capture", () => {
    // Given / When
    const params = ticketToCaptureParams(
      ticket({ mode: "1ch", source: "device", range: "5v", label: "точка-7" }),
    );

    // Then
    expect(params).toMatchObject({
      mode: "single_channel",
      source: "device",
      duration_s: "2.4",
      sample_rate_hz: "8000000",
      range_v: "5",
      label: "точка-7",
    });
  });

  it("2ch — двухканальный RC-режим, sim — симулятор", () => {
    // Given / When
    const params = ticketToCaptureParams(ticket({ mode: "2ch", source: "sim" }));

    // Then
    expect(params.mode).toBe("rc_measurement");
    expect(params.source).toBe("simulator");
  });

  it("±2 В маппится в ближайший допустимый диапазон 1 В (честный фолбэк, не молча)", () => {
    // Given / When
    const params = ticketToCaptureParams(ticket({ range: "2v" }));

    // Then
    expect(params.range_v).toBe("1");
  });

  it("пустая метка в билет не попадает (capture покажет пустое поле, а не пробелы)", () => {
    // Given / When
    const params = ticketToCaptureParams(ticket({ label: "   " }));

    // Then
    expect(params).not.toContain("label");
  });

  it("неизвестные значения режима/источника/диапазона отбрасываются, остальное живёт", () => {
    // Given / When
    const params = ticketToCaptureParams(
      ticket({ mode: "9ch", source: "эфир", range: "220v", duration: "1.0" }),
    );

    // Then
    expect(params).not.toContain("mode");
    expect(params).not.toContain("source");
    expect(params).not.toContain("range_v");
    expect(params.duration_s).toBe("1.0");
  });
});
