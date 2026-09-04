/** Подписи шкалы спектрограммы в дБВ/Гц с опорой «отн. 1 В²/Гц» + ref-уровень.
 * RED: scale/readout/tooltip/visualMap называют единицу PSD, дельта — честный min/max. */

import { afterEach, describe, expect, it, vi } from "vitest";
import { gramScaleText } from "../../capture/spectrogramLivePaint";
import { buildSpectrogramLiveRenderer } from "../../capture/spectrogramLiveRenderer";
import type { SpectrogramChartOption } from "../../components/charts/echarts";
import { scaleText } from "./inspectV6Gram";
import type { OrientedChart } from "./spectrogramOrient";
import { createOrientedSpectrogramView } from "./spectrogramOrient";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function lastOption(recorded: SpectrogramChartOption[]): SpectrogramChartOption {
  const option = recorded[recorded.length - 1];
  if (option === undefined) throw new Error("no recorded option");
  return option;
}

function tooltipText(
  option: SpectrogramChartOption,
  data: readonly [number, number, number],
): string {
  const tooltip = isRecord(option.tooltip) ? option.tooltip : undefined;
  const formatter = tooltip?.formatter;
  if (typeof formatter !== "function") throw new Error("no tooltip formatter");
  return String((formatter as (params: unknown) => unknown)({ data: [...data] }));
}

function visualMapText(option: SpectrogramChartOption): unknown {
  const visualMap = Array.isArray(option.visualMap) ? option.visualMap[0] : option.visualMap;
  return isRecord(visualMap) ? visualMap.text : undefined;
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

function logFreqs(count: number, minHz = 10, maxHz = 10_000_000): number[] {
  const lo = Math.log10(minHz);
  const hi = Math.log10(maxHz);
  return Array.from({ length: count }, (_, i) => 10 ** (lo + ((hi - lo) * i) / (count - 1)));
}

describe("inspectV6Gram scaleText: дБВ/Гц и честный диапазон дельты", () => {
  it("режимы А/Б называют дБВ/Гц с опорой 1 В²/Гц", () => {
    const text = scaleText("a", {
      kind: "tile",
      tile: {
        times: new Float64Array([0]),
        freqs: new Float64Array([1000]),
        values: new Float32Array([-50]),
      },
      minDb: -90,
      maxDb: -30,
    });
    expect(text).toContain("дБВ/Гц");
    expect(text).toContain("1 В²/Гц");
  });

  it("дельта показывает честный min/max, а не симметризацию ±max", () => {
    const text = scaleText("delta", {
      kind: "tile",
      tile: {
        times: new Float64Array([0]),
        freqs: new Float64Array([1000]),
        values: new Float32Array([6]),
      },
      minDb: -2,
      maxDb: 6,
    });
    expect(text).toContain("−2");
    expect(text).toContain("+6");
    expect(text).not.toContain("−6");
  });
});

describe("spectrogramOrient: tooltip и visualMap в дБВ/Гц", () => {
  const views: Array<{ dispose: () => void }> = [];
  afterEach(() => {
    for (const view of views) view.dispose();
    views.length = 0;
    document.body.replaceChildren();
  });

  it("tooltip и visualMap называют дБВ/Гц с опорой", () => {
    const recorded: SpectrogramChartOption[] = [];
    const view = createOrientedSpectrogramView({ init: makeFakeInit(recorded) });
    views.push(view);
    view.setDomain({
      timeS: new Float64Array([0, 1]),
      frequencyHz: new Float64Array([100, 1000]),
    });
    const option = lastOption(recorded);
    expect(tooltipText(option, [1, 0, -50])).toContain("дБВ/Гц");
    expect(tooltipText(option, [1, 0, -50])).toContain("1 В²/Гц");
    expect(JSON.stringify(visualMapText(option))).toContain("дБВ/Гц");
  });
});

describe("live-шкала: дБВ/Гц для уровней, дБ для дельты", () => {
  it("gramScaleText уровня — дБВ/Гц с опорой, дельты — дБ", () => {
    const level = gramScaleText("b", { low: -90.4, high: -30.2 });
    expect(level).toContain("дБВ/Гц");
    expect(level).toContain("1 В²/Гц");
    expect(gramScaleText("delta", { low: -3, high: 3 })).toContain("дБ");
  });

  it("readout live-рендера — дБВ/Гц", () => {
    const renderer = buildSpectrogramLiveRenderer();
    try {
      document.body.append(renderer.host);
      const canvas = renderer.host.querySelector("[data-spectrogram-canvas]") as HTMLCanvasElement;
      const readout = renderer.bar.querySelector("[data-spectrogram-readout]") as HTMLElement;
      vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 400, 200));
      const freqs = logFreqs(64);
      renderer.pushSpectrumColumn(
        freqs,
        freqs.map(() => -50),
      );
      canvas.dispatchEvent(new MouseEvent("mousemove", { clientX: 200, clientY: 100 }));
      expect(readout.textContent).toContain("дБВ/Гц");
    } finally {
      renderer.dispose();
      document.body.replaceChildren();
    }
  });
});
