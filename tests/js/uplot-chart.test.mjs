import assert from "node:assert/strict";
import test from "node:test";

import { dashPattern, logSafePairs, UPLOT_VERSION } from "../../src/lnt/ui/static/uplot-chart.js";

test("logSafePairs отбрасывает пары с нулями, отрицательными и нечисловыми значениями", () => {
  const x = [10, 0, -5, 20, Number.NaN, 40, Number.POSITIVE_INFINITY];
  const y = [1e-3, 2e-3, 3e-3, 0, 5e-3, Number.NaN, 7e-3];
  const pairs = logSafePairs(x, y);
  assert.deepEqual(pairs.x, [10]);
  assert.deepEqual(pairs.y, [1e-3]);
});

test("logSafePairs устойчив к разной длине входов (минимум пар)", () => {
  const pairs = logSafePairs([1, 2, 3, 4], [1, 2]);
  assert.deepEqual(pairs.x, [1, 2]);
  assert.deepEqual(pairs.y, [1, 2]);
});

test("dashPattern отображает стили линии на шаблоны штрихов uPlot", () => {
  assert.deepEqual(dashPattern("dash"), [6, 4]);
  assert.deepEqual(dashPattern("dot"), [2, 3]);
  assert.equal(dashPattern("solid"), undefined);
  assert.equal(dashPattern(undefined), undefined);
});

test("вендоренный uPlot идентифицирует свою версию в заголовке модуля", async () => {
  // Версия зафиксирована константой адаптера и сверяется с файлом вендора.
  const { readFileSync } = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  const path = fileURLToPath(new URL("../../src/lnt/ui/static/vendor/uPlot.esm.js", import.meta.url));
  const head = readFileSync(path, "utf8").slice(0, 400).toLowerCase();
  assert.match(head, /uplot\.js/);
  assert.equal(UPLOT_VERSION, "1.6.32");
});
