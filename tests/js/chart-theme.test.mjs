import assert from "node:assert/strict";
import { test } from "node:test";

import { createChartRenderer } from "../../src/lnt/ui/static/chart-views.js";

const SPECTRUM = { frequency_hz: [10, 20, 30], psd_v2_per_hz: [1, 2, 3] };

function harness() {
  const target = {
    dataset: {},
    attrs: { "aria-describedby": "spectrum-status" },
    getAttribute(name) {
      return this.attrs[name] ?? null;
    },
    setAttribute(name, value) {
      this.attrs[name] = String(value);
    },
    replaceChildren() {},
    contains: () => false,
    append() {},
    getBoundingClientRect: () => ({ width: 640, height: 260 }),
  };
  const status = { textContent: "" };
  const byId = { "spectrum-plot": target, "spectrum-status": status };
  const reactCalls = [];
  const chartLib = {
    newPlot: async () => ({}),
    react: (node, _traces, layout) => {
      reactCalls.push({ node, layout });
    },
  };
  let tokens = { lineA: "#1", grid: "#3", plot: "#4", paper: "#light", text: "#6", lineWidth: 1 };
  const renderer = createChartRenderer({
    loadChart: async () => chartLib,
    getElementById: (id) => byId[id] ?? null,
    readPlotTokens: () => tokens,
  });
  return {
    renderer,
    reactCalls,
    target,
    setTokens: (next) => {
      tokens = next;
    },
  };
}

test("applyTheme repaints an already-rendered plot with fresh tokens and no refetch", async () => {
  const h = harness();
  await h.renderer.plotSpectrum("spectrum-plot", SPECTRUM);
  assert.equal(h.target.dataset.chartState, "ready");
  h.setTokens({ lineA: "#a", grid: "#c", plot: "#d", paper: "#dark", text: "#f", lineWidth: 2 });
  h.renderer.applyTheme();
  assert.equal(h.reactCalls.length, 1);
  assert.equal(h.reactCalls[0].node, h.target);
  assert.equal(h.reactCalls[0].layout.paper_bgcolor, "#dark");
});

test("applyTheme is a safe no-op when no plot has been rendered yet", () => {
  const h = harness();
  assert.doesNotThrow(() => h.renderer.applyTheme());
  assert.equal(h.reactCalls.length, 0);
});

test("applyTheme skips a chart that is not in the ready state", async () => {
  const h = harness();
  await h.renderer.plotSpectrum("spectrum-plot", SPECTRUM);
  h.target.dataset.chartState = "loading";
  h.renderer.applyTheme();
  assert.equal(h.reactCalls.length, 0);
});
