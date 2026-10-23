import { describe, expect, it } from "vitest";
import type { CaptureFormValues } from "./modes";
import { CAPTURE_MODES, DEFAULT_FORM_VALUES, buildJobRequest, validateCaptureForm } from "./modes";

const valid = { ...DEFAULT_FORM_VALUES };

describe("capture mode definitions", () => {
  it("exposes exactly the five planned modes", () => {
    expect(Object.keys(CAPTURE_MODES).sort()).toEqual(
      [
        "line_quality",
        "rc_measurement",
        "self_noise",
        "single_channel",
        "ripple_measurement",
      ].sort(),
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
    expect(CAPTURE_MODES.ripple_measurement.channels).toBe(1);
    expect(CAPTURE_MODES.ripple_measurement.usesBaseline).toBe(false);
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

describe("validateCaptureForm: поля декларации адаптера", () => {
  it("принимает дефолтные значения декларации без ошибок", () => {
    const { valid: parsedDefault, errors } = validateCaptureForm(valid);
    expect(errors.adapterCapNf).toBeUndefined();
    expect(errors.adapterSeriesROhm).toBeUndefined();
    expect(errors.adapterBasis).toBeUndefined();
    expect(parsedDefault?.adapterCapNf).toBe(100);
    expect(parsedDefault?.adapterSeriesROhm).toBe(0);
    expect(valid?.adapterPreconnected).toBe(false);
    expect(valid?.adapterBasis).toBe("nominal");
  });

  it("режет неположительную ёмкость и отрицательный R по-русски", () => {
    const { errors } = validateCaptureForm({
      ...valid,
      adapterCapNf: "0",
      adapterSeriesROhm: "-1",
    });
    expect(errors.adapterCapNf).toContain("положительным числом нанофарад");
    expect(errors.adapterSeriesROhm).toContain("неотрицательным числом ом");
  });

  it("базис значений — только литерал nominal/operator_measured", () => {
    const bogus = JSON.parse(
      JSON.stringify({ ...valid, adapterBasis: "value_diff" }),
    ) as CaptureFormValues;
    const { errors } = validateCaptureForm(bogus);
    expect(errors.adapterBasis).toContain("номинал");
  });
});

describe("buildJobRequest: ветка adapter_declaration", () => {
  const parsed = validateCaptureForm({ ...valid }).valid;
  if (!parsed) throw new Error("fixture must validate");

  it("ripple_measurement + device вкладывает adapter_declaration в capture-запрос", () => {
    const ripple = validateCaptureForm({
      ...valid,
      adapterCapNf: "220",
      adapterSeriesROhm: "4.7",
      adapterPreconnected: true,
      adapterBasis: "operator_measured",
    }).valid;
    if (!ripple) throw new Error("fixture must validate");
    const request = buildJobRequest(CAPTURE_MODES.ripple_measurement, ripple, "device");
    expect(request).toMatchObject({
      kind: "capture",
      channels: 1,
      input: "rc",
      adapter_declaration: {
        preconnected: true,
        cap_nf: 220,
        series_r_ohm: 4.7,
        component_values_basis: "operator_measured",
      },
    });
  });

  it("симулятор никогда не несёт декларацию (D7)", () => {
    const request = buildJobRequest(CAPTURE_MODES.ripple_measurement, parsed, "simulator");
    expect(request.kind).toBe("simulate");
    expect("adapter_declaration" in request).toBe(false);
  });

  it("прочие режимы с устройством не несут декларацию", () => {
    for (const id of ["rc_measurement", "self_noise", "line_quality", "single_channel"] as const) {
      const request = buildJobRequest(CAPTURE_MODES[id], parsed, "device");
      expect("adapter_declaration" in request).toBe(false);
    }
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
