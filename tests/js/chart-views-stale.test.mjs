import assert from "node:assert/strict";
import test from "node:test";

import { createChartRenderer } from "../../src/lnt/ui/static/chart-views.js";

function deferred() {
  let rejectPromise;
  let resolvePromise;
  const promise = new Promise((resolve, reject) => {
    rejectPromise = reject;
    resolvePromise = resolve;
  });
  return { promise, reject: rejectPromise, resolve: resolvePromise };
}

function setup(plotPromise, nextPlot) {
  const block = { hidden: false };
  const figure = { hidden: false, parentElement: block };
  const target = {
    attributes: new Map([["aria-busy", "false"], ["aria-describedby", "chart-status"]]),
    children: ["existing"],
    dataset: { chartState: "idle" },
    hidden: false,
    parentElement: figure,
    getAttribute(name) { return this.attributes.get(name); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
  };
  const status = { textContent: "" };
  const plotCalls = [];
  const renderer = createChartRenderer({
    getElementById: (id) => id === "chart-status" ? status : target,
    loadChart: async () => ({
      newPlot(...args) {
        plotCalls.push(args);
        return nextPlot === undefined ? plotPromise : nextPlot();
      },
    }),
    readPlotTokens: () => ({
      grid: "grid", lineA: "a", lineB: "b", lineWidth: 2,
      paper: "paper", plot: "plot", text: "text",
    }),
  });
  return { plotCalls, renderer, status, target };
}

test("stale spectrum completion does not set ready or clear live status", async () => {
  const plot = deferred();
  const context = setup(plot.promise);
  let current = true;
  const operation = context.renderer.plotSpectrum(
    "spectrum-plot",
    { frequency_hz: [1], psd_v2_per_hz: [1] },
    { isCurrent: () => current },
  );
  await Promise.resolve();
  assert.equal(context.plotCalls.length, 1);
  current = false;

  plot.resolve();
  await operation;

  assert.equal(context.target.dataset.chartState, "loading");
  assert.equal(context.target.getAttribute("aria-busy"), "true");
  assert.equal(context.status.textContent, "Загрузка графика…");
});

function setupQueue(plots) {
  const queue = [...plots];
  return setup(undefined, () => queue.shift().promise);
}

test("a queued newer render repaints the chart after a stale settle", async () => {
  const plots = [deferred(), deferred()];
  const context = setupQueue(plots);
  let firstCurrent = true;
  const first = context.renderer.plotWaveform(
    "waveform-plot",
    { channel: "ch1", time_s: [0], voltage_v: [1] },
    { isCurrent: () => firstCurrent },
  );
  await Promise.resolve();
  assert.equal(context.plotCalls.length, 1);
  firstCurrent = false;

  const second = context.renderer.plotWaveform(
    "waveform-plot",
    { channel: "ch2", time_s: [1], voltage_v: [2] },
    { isCurrent: () => true },
  );
  await Promise.resolve();
  assert.equal(context.plotCalls.length, 1);

  plots[0].resolve("first");
  await first;
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(context.plotCalls.length, 2);
  assert.equal(context.target.dataset.chartState, "loading");

  plots[1].resolve("second");
  assert.equal(await second, "second");
  assert.equal(context.target.dataset.chartState, "ready");
  assert.equal(context.target.getAttribute("aria-busy"), "false");
  assert.equal(context.status.textContent, "");
});

test("failChart resolves a dangling loading state to an explicit error", async () => {
  const plot = deferred();
  const context = setup(plot.promise);
  let current = true;
  const operation = context.renderer.plotWaveform(
    "waveform-plot",
    { channel: "ch1", time_s: [0], voltage_v: [1] },
    { isCurrent: () => current },
  );
  await Promise.resolve();
  current = false;
  plot.resolve();
  await operation;
  assert.equal(context.target.dataset.chartState, "loading");

  context.renderer.failChart("waveform-plot");

  assert.equal(context.target.dataset.chartState, "error");
  assert.equal(context.target.getAttribute("aria-busy"), "false");
  assert.deepEqual(context.target.children, []);
  assert.equal(context.status.textContent, "Не удалось загрузить график. Повторите открытие сессии.");
});

test("failChart is a no-op on a ready chart", async () => {
  const plot = deferred();
  const context = setup(plot.promise);
  const operation = context.renderer.plotSpectrum(
    "spectrum-plot",
    { frequency_hz: [1], psd_v2_per_hz: [1] },
    { isCurrent: () => true },
  );
  plot.resolve("ready");
  await operation;
  assert.equal(context.target.dataset.chartState, "ready");

  context.renderer.failChart("spectrum-plot");

  assert.equal(context.target.dataset.chartState, "ready");
  assert.deepEqual(context.target.children, ["existing"]);
  assert.equal(context.status.textContent, "");
});

test("stale waveform rejection does not set error or announce failure", async () => {
  const plot = deferred();
  const context = setup(plot.promise);
  let current = true;
  const operation = context.renderer.plotWaveform(
    "waveform-plot",
    { channel: "ch1", time_s: [0], voltage_v: [1] },
    { isCurrent: () => current },
  );
  await Promise.resolve();
  assert.equal(context.plotCalls.length, 1);
  current = false;

  plot.reject(new Error("stale plot"));
  await assert.rejects(operation, /stale plot/);

  assert.equal(context.target.dataset.chartState, "loading");
  assert.equal(context.target.getAttribute("aria-busy"), "true");
  assert.deepEqual(context.target.children, ["existing"]);
  assert.equal(context.status.textContent, "Загрузка графика…");
});
