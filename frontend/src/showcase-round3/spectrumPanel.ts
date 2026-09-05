/** Панель спектра раунда 3: uPlot-пара A/B (рендерер redesign), маска поверх,
 *  маркерные чипы и дельта-полоса — сигнатура пары в одном блоке. */
import { type SpectrumStyle, renderSpectrum } from "../showcase-redesign/spectrum";
import { PAIR_SUMMARY } from "./data";
import { buildDeltaStrip } from "./deltaStrip";
import { buildMarkerChips, h } from "./kit";
import { drawLimitMask } from "./limits";

export interface PanelPalette {
  traceA: string;
  traceB: string;
}

function styleFor(palette: PanelPalette): SpectrumStyle {
  return {
    traceA: palette.traceA,
    traceB: palette.traceB,
    grid: "rgba(255,255,255,0.08)",
    axisText: "#8e8e8e",
    lineWidth: 2,
    dash: [6, 4],
    axisFont: '500 10px "JetBrains Mono Variable", monospace',
    height: 320,
    xLabel: "",
  };
}

/** Собирает панель: шапка (чипы+ридеут монтирует рендерер), график, маркеры, Δ-полоса. */
export function buildSpectrumPanel(palette: PanelPalette): HTMLElement {
  const header = h("div", "panel-head", {}, [h("h2", "panel-title", {}, ["Спектр мощности"])]);
  const host = h("div", "spectrum-host", { "data-r3": "spectrum" });
  const panel = h("section", "panel", {}, [header, host, buildMarkerChips(), buildDeltaStrip()]);
  renderSpectrum(
    host,
    styleFor(palette),
    { a: `A ${PAIR_SUMMARY.a.label}`, b: `B ${PAIR_SUMMARY.b.label}` },
    { header, onDraw: drawLimitMask },
  );
  return panel;
}
