import assert from "node:assert/strict";
import test from "node:test";

import {
  PLOTLY_SOURCE,
  createPlotlyLoader,
} from "../../src/lnt/ui/static/plotly-loader.js";

class FakeScript {
  constructor() {
    this.dataset = {};
    this.defer = false;
    this.onload = null;
    this.onerror = null;
    this.removed = false;
    this.src = "";
  }

  remove() {
    this.removed = true;
  }
}

class FakeDocument {
  constructor() {
    this.scripts = [];
    this.head = {
      append: (script) => this.scripts.push(script),
    };
  }

  createElement(tagName) {
    assert.equal(tagName, "script");
    return new FakeScript();
  }
}

function setup(plotly) {
  const documentRef = new FakeDocument();
  const globalRef = { Plotly: plotly };
  const loadPlotly = createPlotlyLoader({ documentRef, globalRef });
  return { documentRef, globalRef, loadPlotly };
}

function assertReadableError(error) {
  return error instanceof Error && error.message.trim().length > 0;
}

test("returns an existing Plotly object without adding a script", async () => {
  const plotly = { newPlot() {} };
  const { documentRef, loadPlotly } = setup(plotly);

  assert.strictEqual(await loadPlotly(), plotly);
  assert.equal(documentRef.scripts.length, 0);
});

test("shares one local script and one in-flight promise between concurrent calls", async () => {
  const { documentRef, globalRef, loadPlotly } = setup(undefined);

  const firstLoad = loadPlotly();
  const secondLoad = loadPlotly();

  assert.strictEqual(firstLoad, secondLoad);
  assert.equal(documentRef.scripts.length, 1);
  const [script] = documentRef.scripts;
  assert.equal(PLOTLY_SOURCE, "/static/vendor/plotly-gl2d-3.7.0.min.js");
  assert.equal(script.src, PLOTLY_SOURCE);
  assert.equal(script.defer, true);
  assert.equal(script.dataset.lntPlotly, "true");

  const plotly = { newPlot() {} };
  globalRef.Plotly = plotly;
  script.onload();

  const [firstResult, secondResult] = await Promise.all([firstLoad, secondLoad]);
  assert.strictEqual(firstResult, plotly);
  assert.strictEqual(secondResult, plotly);
});

test("rejects a script error, clears failed state, and permits a successful retry", async () => {
  const { documentRef, globalRef, loadPlotly } = setup(undefined);
  const failedLoad = loadPlotly();
  const firstScript = documentRef.scripts[0];

  firstScript.onerror();

  await assert.rejects(failedLoad, assertReadableError);
  assert.equal(firstScript.removed, true);

  const retryLoad = loadPlotly();
  assert.equal(documentRef.scripts.length, 2);
  assert.notStrictEqual(retryLoad, failedLoad);
  const retryScript = documentRef.scripts[1];
  const plotly = { newPlot() {} };
  globalRef.Plotly = plotly;
  retryScript.onload();

  assert.strictEqual(await retryLoad, plotly);
});

test("rejects load without valid Plotly, clears cache, and permits retry", async () => {
  const { documentRef, globalRef, loadPlotly } = setup(undefined);
  const failedLoad = loadPlotly();
  const firstScript = documentRef.scripts[0];

  globalRef.Plotly = {};
  firstScript.onload();

  await assert.rejects(failedLoad, assertReadableError);
  assert.equal(firstScript.removed, true);

  const retryLoad = loadPlotly();
  assert.equal(documentRef.scripts.length, 2);
  const retryScript = documentRef.scripts[1];
  const plotly = { newPlot() {} };
  globalRef.Plotly = plotly;
  retryScript.onload();

  assert.strictEqual(await retryLoad, plotly);
});
