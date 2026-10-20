/** Опции uPlot: подписи оси X из ChartRenderRequest.xTick (формат + шаг).
 *  Частотный спектр задаёт короткий формат, остальные графики — умолчания. */

import { describe, expect, it } from "vitest";
import type { ChartTheme } from "./theme";
import type { ChartRenderRequest } from "./types";
import { buildUplotOptions } from "./uplotOptions";

const THEME: ChartTheme = {
  accentA: "#5681ff",
  accentB: "#e68619",
  delta: "#b7a6ff",
  ok: "#3dbd8a",
  panel: "#323232",
  canvasBg: "#1d1d1d",
  fgSecondary: "#d1d1d1",
  borderSubtle: "#3f3f3f",
  fontMono: '"IBM Plex Mono", Consolas, monospace',
  fontSans: '"IBM Plex Sans", sans-serif',
  lineWidth: 1,
};

function request(overrides: Partial<ChartRenderRequest> = {}): ChartRenderRequest {
  return {
    xLabel: "Частота, Гц",
    yLabel: "Уровень, дБ",
    x: [0, 1_000_000, 4_000_000],
    series: [{ label: "Трасса", values: [0, -10, -20], color: "#5681ff" }],
    ...overrides,
  };
}

function build(req: ChartRenderRequest) {
  return buildUplotOptions({
    request: req,
    theme: THEME,
    width: 800,
    height: 400,
    syncKey: "test",
    onCursor: () => undefined,
  });
}

describe("опции осей uPlot", () => {
  it("xTick форматирует подписи и задаёт шаг", () => {
    const options = build(
      request({ xTick: { format: (value) => `${value / 1000} кГц`, space: 64 } }),
    );
    const axis = options.axes?.[0];
    expect(axis?.space).toBe(64);
    const values = axis?.values;
    if (typeof values !== "function") throw new Error("values не задан");
    expect(values({} as never, [0, 250_000, 4_000_000], 0, 64, 250_000)).toEqual([
      "0 кГц",
      "250 кГц",
      "4000 кГц",
    ]);
  });

  it("без xTick остаются умолчания uPlot (values и space не переопределены)", () => {
    const options = build(request());
    const axis = options.axes?.[0];
    expect(axis?.space).toBeUndefined();
    expect(axis?.values).toBeUndefined();
  });
});
