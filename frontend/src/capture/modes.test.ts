import { describe, expect, it } from "vitest";
import { CAPTURE_MODES, DEFAULT_FORM_VALUES, buildJobRequest, validateCaptureForm } from "./modes";

const valid = { ...DEFAULT_FORM_VALUES };

describe("capture mode definitions", () => {
  it("exposes exactly the four planned modes", () => {
    expect(Object.keys(CAPTURE_MODES).sort()).toEqual(
      ["line_quality", "rc_measurement", "self_noise", "single_channel"].sort(),
    );
  });

  it("locks impossible combinations out of the mode table", () => {
    expect(CAPTURE_MODES.line_quality.channels).toBe(1);
    expect(CAPTURE_MODES.line_quality.input).toBe("transformer");
    expect(CAPTURE_MODES.line_quality.usesBaseline).toBe(false);
    expect(CAPTURE_MODES.self_noise.usesBaseline).toBe(false);
    expect(CAPTURE_MODES.self_noise.selfNoise).toBe(true);
    expect(CAPTURE_MODES.rc_measurement.channels).toBe(2);
    expect(CAPTURE_MODES.single_channel.channels).toBe(1);
    expect(CAPTURE_MODES.single_channel.usesBaseline).toBe(true);
  });
});

describe("validateCaptureForm", () => {
  it("accepts defaults with zero errors", () => {
    const { valid: parsed, errors } = validateCaptureForm(valid);
    expect(errors).toEqual({});
    expect(parsed?.durationS).toBeCloseTo(2.4);
    expect(parsed?.rangeV).toBe(5);
    expect(parsed?.repeat).toBe(1);
  });

  it("rejects non-positive duration and rate in Russian", () => {
    const { errors } = validateCaptureForm({ ...valid, durationS: "0", sampleRateHz: "-5" });
    expect(errors.durationS).toContain("положительным числом");
    expect(errors.sampleRateHz).toContain("положительным числом");
  });

  it("rejects unsupported range like the backend validator", () => {
    const { errors } = validateCaptureForm({ ...valid, rangeV: "2" });
    expect(errors.rangeV).toBe("Диапазон должен быть одним из: 5, 1 или 0,5 В.");
  });

  it("rejects fractional repeat and negative interval", () => {
    const { errors } = validateCaptureForm({ ...valid, repeat: "1.5", intervalS: "-1" });
    expect(errors.repeat).toContain("целое число не меньше 1");
    expect(errors.intervalS).toContain("неотрицательным");
  });

  it("rejects unsafe baseline session names (mirror of _validated_child_name)", () => {
    const { errors } = validateCaptureForm({ ...valid, baselineSession: "../escape" });
    expect(errors.baselineSession).toContain("Имя базовой сессии");
    const ok = validateCaptureForm({ ...valid, baselineSession: "selfnoise-001" });
    expect(ok.valid?.baselineSession).toBe("selfnoise-001");
  });

  it("rejects overlong labels", () => {
    const { errors } = validateCaptureForm({ ...valid, label: "x".repeat(129) });
    expect(errors.label).toContain("128 символов");
  });
});

describe("buildJobRequest", () => {
  const parsed = validateCaptureForm({
    ...valid,
    label: "стенд-А",
    baselineSession: "base-1",
    repeat: "3",
    intervalS: "2",
  }).valid;
  if (!parsed) throw new Error("fixture must validate");

  it("maps rc_measurement to dual-channel capture with baseline", () => {
    const request = buildJobRequest(CAPTURE_MODES.rc_measurement, parsed, "device");
    expect(request).toMatchObject({
      kind: "capture",
      input: "rc",
      channels: 2,
      self_noise: false,
      baseline_session: "base-1",
      repeat: 3,
      interval_s: 2,
      label: "стенд-А",
    });
  });

  it("maps self_noise to terminated capture without baseline", () => {
    const request = buildJobRequest(CAPTURE_MODES.self_noise, parsed, "device");
    expect(request).toMatchObject({
      kind: "capture",
      self_noise: true,
      baseline_session: null,
      channels: 2,
    });
  });

  it("maps line_quality to single-channel transformer capture", () => {
    const request = buildJobRequest(CAPTURE_MODES.line_quality, parsed, "device");
    expect(request).toMatchObject({
      kind: "capture",
      input: "transformer",
      channels: 1,
      self_noise: false,
      baseline_session: null,
    });
  });

  it("maps simulator source to a simulate request with profile", () => {
    const request = buildJobRequest(CAPTURE_MODES.rc_measurement, parsed, "simulator");
    expect(request).toMatchObject({
      kind: "simulate",
      profile: "quiet",
      channels: 2,
      repeat: 3,
      interval_s: 2,
    });
    // Симулятор не передаёт железные поля осциллографа.
    expect("range_v" in request).toBe(false);
    expect("baseline_session" in request).toBe(false);
  });
});
