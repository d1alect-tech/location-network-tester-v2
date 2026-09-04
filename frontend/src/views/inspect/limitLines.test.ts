import { describe, expect, it } from "vitest";
import { curveVerdict, evaluateMask, parseLimitMask, spcVerdict } from "./limitLines";

/** Given / When / Then: B4 limit-lines mirror the backend analytic truth. */

describe("curveVerdict", () => {
  it("holds the ITIC boundary durations", () => {
    expect(curveVerdict(0.02, 0.0, "itic")).toBe("pass");
    expect(curveVerdict(0.5, 0.7, "itic")).toBe("pass");
    expect(curveVerdict(0.2, 0.6, "itic")).toBe("fail");
  });

  it("holds the SEMI-F47 boundary durations", () => {
    expect(curveVerdict(0.2, 0.5, "semi_f47")).toBe("pass");
    expect(curveVerdict(0.5, 0.7, "semi_f47")).toBe("pass");
    expect(curveVerdict(1.0, 0.8, "semi_f47")).toBe("pass");
    expect(curveVerdict(0.5, 0.6, "semi_f47")).toBe("fail");
  });

  it("is unavailable on bad inputs, never fabricated", () => {
    expect(curveVerdict(Number.NaN, 1.0, "itic")).toBe("unavailable");
    expect(curveVerdict(-1, 1.0, "semi_f47")).toBe("unavailable");
  });
});

describe("evaluateMask", () => {
  const mask = {
    name: "psd-mask",
    unit: "db",
    points: [
      { x: 10, y: -40 },
      { x: 100, y: -50 },
    ],
  };

  it("passes below the line and fails above it", () => {
    expect(evaluateMask(10, -50, mask)).toBe("pass");
    expect(evaluateMask(10, -30, mask)).toBe("fail");
  });

  it("is unavailable outside the domain or without data", () => {
    expect(evaluateMask(5, -60, mask)).toBe("unavailable");
    expect(evaluateMask(10, Number.NaN, mask)).toBe("unavailable");
    expect(parseLimitMask({ name: "x", unit: "db", points: [] })?.points).toEqual([]);
  });
});

describe("spcVerdict", () => {
  it("passes inside k-sigma and fails outside, unavailable without sigma", () => {
    expect(spcVerdict(0, 0, 1)).toBe("pass");
    expect(spcVerdict(5, 0, 1)).toBe("fail");
    expect(spcVerdict(0, 0, 0)).toBe("unavailable");
  });
});
