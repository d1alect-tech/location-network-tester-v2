import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { expect, test } from "@playwright/test";

/** Бенчмарк uPlot 1-D (todo 41): бюджеты на 200 000 отображённых точек —
 * первичный рендер ≤1000 мс, пан/зум p95 ≤100 мс. Результаты пишутся в
 * %TEMP% (+ копия в LNT_BENCH_OUT, если задан); замороженные
 * bench/DECISION.md и bench/results.json никогда не перезаписываются. */

interface WindowWithBench extends Window {
  runUplotBenchmark?: (pointCount: number) => Promise<{
    pointCount: number;
    wireSizeBytes: number;
    dataGenMs: number;
    renderMs: number;
    panP95Ms: number;
    zoomP95Ms: number;
    teardownMs: number;
    panMeanMs: number;
    zoomMeanMs: number;
    renderedPoints: number;
    paintedPixelSamples: number;
  }>;
}

const BUDGET_INITIAL_MS = 1_000;
const BUDGET_INTERACT_P95_MS = 100;
const BUDGET_POINTS = 200_000;

test("uPlot 1-D budgets at 200k points", async ({ page }) => {
  await page.goto("http://127.0.0.1:4103/static/v2/bench/uplot-bench.html");
  await page.waitForFunction(
    () => (window as unknown as WindowWithBench).runUplotBenchmark !== undefined,
  );

  const context = page.context();
  const client = await context.newCDPSession(page);
  await client.send("Performance.enable");

  const results: Array<Record<string, number>> = [];
  for (const count of [50_000, BUDGET_POINTS]) {
    console.log(`[uplot-bench] ${count} points...`);
    const result = await page.evaluate(async (c) => {
      return await (window as unknown as WindowWithBench).runUplotBenchmark!(c);
    }, count);

    const metrics = await client.send("Performance.getMetrics");
    const map: Record<string, number> = {};
    for (const m of metrics.metrics) map[m.name] = m.value;
    const heapUsedMiB = (map.JSHeapUsedSize ?? 0) / (1024 * 1024);

    let browserRssMiB = 0;
    try {
      const psCommand =
        "powershell -NoProfile -Command \"(Get-CimInstance Win32_Process -Filter '(Name = ''chrome.exe'' or Name = ''chrome-headless-shell.exe'') and ExecutablePath like ''%ms-playwright%''').WorkingSetSize | Measure-Object -Sum | Select-Object -ExpandProperty Sum\"";
      const output = execSync(psCommand, { encoding: "utf-8" }).trim();
      browserRssMiB = Number.parseInt(output, 10) / (1024 * 1024);
    } catch (error) {
      console.error("[uplot-bench] RSS measurement failed:", error);
    }

    results.push({ ...result, heapUsedMiB, browserRssMiB });
  }

  const at200k = results.find((r) => r.pointCount === BUDGET_POINTS) ?? results.at(-1)!;
  // Жёсткие бюджеты плана (todo 41) на ≥200k точек + честность рендера:
  // точки закреплены в инстансе, канва действительно покрашена.
  expect(at200k.renderedPoints).toBe(BUDGET_POINTS);
  expect(at200k.paintedPixelSamples).toBeGreaterThan(0);
  expect(at200k.renderMs).toBeLessThanOrEqual(BUDGET_INITIAL_MS);
  expect(at200k.panP95Ms).toBeLessThanOrEqual(BUDGET_INTERACT_P95_MS);
  expect(at200k.panMeanMs).toBeLessThanOrEqual(BUDGET_INTERACT_P95_MS);
  expect(at200k.zoomP95Ms).toBeLessThanOrEqual(BUDGET_INTERACT_P95_MS);
  expect(at200k.zoomMeanMs).toBeLessThanOrEqual(BUDGET_INTERACT_P95_MS);

  const host = {
    os: `${os.type()} ${os.release()} ${os.arch()}`,
    cpu: os.cpus()[0]?.model ?? "unknown",
    ram_gib: Math.round(os.totalmem() / 2 ** 33),
    node: process.version,
  };
  const payload = {
    bench: "uplot-1d-todo41",
    generated_utc: new Date().toISOString(),
    host,
    budgets: {
      points: BUDGET_POINTS,
      initial_render_ms: BUDGET_INITIAL_MS,
      interact_p95_ms: BUDGET_INTERACT_P95_MS,
    },
    results,
  };

  const tmpPath = path.join(os.tmpdir(), "lnt-uplot-bench-results.json");
  fs.writeFileSync(tmpPath, `${JSON.stringify(payload, null, 2)}\n`);
  console.log(`[uplot-bench] results written to ${tmpPath}`);

  const evidenceDir = process.env.LNT_BENCH_OUT;
  if (evidenceDir !== undefined && evidenceDir !== "") {
    fs.mkdirSync(evidenceDir, { recursive: true });
    const copyPath = path.join(evidenceDir, "bench-results-uplot.json");
    fs.copyFileSync(tmpPath, copyPath);
    console.log(`[uplot-bench] evidence copy written to ${copyPath}`);
  }

  console.log(
    `[uplot-bench] @${BUDGET_POINTS}: render=${at200k.renderMs}ms (≤${BUDGET_INITIAL_MS}), ` +
      `panP95=${at200k.panP95Ms}ms, zoomP95=${at200k.zoomP95Ms}ms (≤${BUDGET_INTERACT_P95_MS})`,
  );
});
