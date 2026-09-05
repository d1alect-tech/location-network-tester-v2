import { afterEach, describe, expect, it } from "vitest";
import type { SpectrogramChartOption } from "../../components/charts/echarts";
import type { OrientedChart } from "./spectrogramOrient";
import { createOrientedSpectrogramView } from "./spectrogramOrient";

type HeatmapCell = readonly [number, number, number];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function axisOf(
  option: SpectrogramChartOption,
  key: "xAxis" | "yAxis",
): Record<string, unknown> | undefined {
  const raw = option[key];
  const axis = Array.isArray(raw) ? raw[0] : raw;
  return isRecord(axis) ? axis : undefined;
}

function heatmapCells(option: SpectrogramChartOption): HeatmapCell[] {
  const series = option.series;
  const first = Array.isArray(series) ? series[0] : series;
  if (!isRecord(first) || !Array.isArray(first.data)) return [];
  const cells: HeatmapCell[] = [];
  for (const row of first.data) {
    if (!Array.isArray(row) || row.length < 3) continue;
    const freqIndex = row[0];
    const timeIndex = row[1];
    const db = row[2];
    if (typeof freqIndex === "number" && typeof timeIndex === "number" && typeof db === "number") {
      cells.push([freqIndex, timeIndex, db]);
    }
  }
  return cells;
}

function makeFakeInit(recorded: SpectrogramChartOption[]) {
  return (_host: HTMLElement): OrientedChart => ({
    setOption(option: SpectrogramChartOption) {
      recorded.push(option);
    },
    resize(): void {},
    dispose(): void {},
  });
}

describe("createOrientedSpectrogramView", () => {
  const views: Array<{ dispose: () => void }> = [];

  afterEach(() => {
    for (const view of views) view.dispose();
    views.length = 0;
    document.body.replaceChildren();
  });

  it("sets frequency on X and inverted time on Y after setDomain", () => {
    // Given: injectable fake chart that records setOption
    const recorded: SpectrogramChartOption[] = [];
    const view = createOrientedSpectrogramView({ init: makeFakeInit(recorded) });
    views.push(view);

    // When
    view.setDomain({
      timeS: new Float64Array([0, 1]),
      frequencyHz: new Float64Array([100, 1000]),
    });

    // Then
    const option = recorded[recorded.length - 1];
    expect(option).toBeDefined();
    if (option === undefined) return;
    const xAxis = axisOf(option, "xAxis");
    const yAxis = axisOf(option, "yAxis");
    expect(xAxis?.name).toBe("Частота, Гц");
    expect(yAxis?.inverse).toBe(true);
    expect(Array.isArray(xAxis?.data) ? xAxis.data.length : 0).toBe(2);
    expect(Array.isArray(yAxis?.data) ? yAxis.data.length : 0).toBe(2);
  });

  it("writes heatmap cells as [freqIndex, timeIndex, db]", () => {
    // Given: 2 freq × 3 time so swapped indices cannot hide in a square
    const recorded: SpectrogramChartOption[] = [];
    const view = createOrientedSpectrogramView({ init: makeFakeInit(recorded) });
    views.push(view);
    view.setDomain({
      timeS: new Float64Array([0, 1, 2]),
      frequencyHz: new Float64Array([100, 1000]),
    });

    // When: values are freq-major (f * nTimes + t), matching sliceTile
    view.renderTile(
      {
        times: new Float64Array([0, 1, 2]),
        freqs: new Float64Array([100, 1000]),
        values: new Float32Array([0, 1, 2, 3, 4, 5]),
      },
      -40,
      -10,
    );

    // Then: cell[0] is freq index (0..1), cell[1] is time index (0..2)
    const option = recorded[recorded.length - 1];
    expect(option).toBeDefined();
    if (option === undefined) return;
    const cells = heatmapCells(option);
    expect(cells.length).toBe(6);
    const freqCount = 2;
    const timeCount = 3;
    for (const cell of cells) {
      expect(cell[0]).toBeGreaterThanOrEqual(0);
      expect(cell[0]).toBeLessThan(freqCount);
      expect(cell[1]).toBeGreaterThanOrEqual(0);
      expect(cell[1]).toBeLessThan(timeCount);
    }
    expect(cells).toContainEqual([1, 2, 5]);
  });

  it("does not put realtime copy in the oriented spectrogram root", () => {
    // Given
    const recorded: SpectrogramChartOption[] = [];
    const view = createOrientedSpectrogramView({ init: makeFakeInit(recorded) });
    views.push(view);

    // When
    view.setDomain({
      timeS: new Float64Array([0, 1]),
      frequencyHz: new Float64Array([100, 1000]),
    });

    // Then
    const html = view.root.innerHTML.toLowerCase();
    expect(html).not.toContain("реалтайм");
    expect(html).not.toContain("realtime");
  });
});
