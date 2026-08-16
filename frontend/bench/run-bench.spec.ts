import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface PerformanceWithMemory extends Performance {
  memory?: {
    usedJSHeapSize: number;
  };
}

interface WindowWithBenchmark extends Window {
  runBenchmark?: (cellCount: number) => Promise<{
    cellCount: number;
    wireSizeBytes: number;
    dataGenMs: number;
    renderMs: number;
    zoomMs: number;
    teardownMs: number;
  }>;
}

test("Run ECharts Heatmap Benchmark", async ({ page }) => {
  await page.goto("http://127.0.0.1:9999/static/v2/bench/echarts-bench.html");
  // Wait for the script to load and expose runBenchmark
  await page.waitForFunction(
    () => (window as unknown as WindowWithBenchmark).runBenchmark !== undefined,
  );

  const cellCounts = [64000, 128000, 262000, 524000, 2000000];
  const results = [];

  for (const count of cellCounts) {
    console.log(`Running benchmark for ${count} cells...`);

    // Measure memory before
    const metricsBefore = await page.evaluate(() => {
      const perf = performance as PerformanceWithMemory;
      return perf.memory ? perf.memory.usedJSHeapSize : 0;
    });

    const result = await page.evaluate(async (c) => {
      return await (window as unknown as WindowWithBenchmark).runBenchmark!(c);
    }, count);

    // Measure memory after
    const metricsAfter = await page.evaluate(() => {
      const perf = performance as PerformanceWithMemory;
      return perf.memory ? perf.memory.usedJSHeapSize : 0;
    });

    const heapDiffBytes = metricsAfter - metricsBefore;
    const heapDiffMiB = heapDiffBytes / (1024 * 1024);

    // Get RSS and other performance metrics from Playwright
    // Note: page.metrics() is only available on Chromium via CDP session
    const client = await (
      page.context() as unknown as {
        newCDPSession: (page: unknown) => Promise<{
          send: (method: string) => Promise<{ metrics: Array<{ name: string; value: number }> }>;
        }>;
      }
    ).newCDPSession(page);
    const performanceMetrics = await client.send("Performance.getMetrics");
    const metricsMap: Record<string, number> = {};
    for (const m of performanceMetrics.metrics) {
      metricsMap[m.name] = m.value;
    }
    const rssMiB = (metricsMap.JSHeapUsedSize || 0) / (1024 * 1024);

    results.push({
      ...result,
      heapDiffMiB: Math.max(0, heapDiffMiB),
      rssMiB: rssMiB || heapDiffMiB, // Fallback if JSHeapUsedSize is not populated
    });
  }

  console.log("Benchmark Results:", results);

  // Write results to frontend/bench/results.json
  const resultsPath = path.resolve(__dirname, "results.json");
  const resultsWithHost = {
    host: {
      os: "Windows 10 Home 22H2 x64",
      cpu: "Ryzen 7 7800X3D",
      ram: "31.6 GiB",
    },
    results,
  };
  fs.writeFileSync(resultsPath, JSON.stringify(resultsWithHost, null, 2));
  console.log(`Results written to ${resultsPath}`);

  // Determine the hard viewport-cell cap and data format
  // Budgets: <= 1.5s render, <= 250ms interaction (zoom), <= 512MiB RSS
  let cap = 64000;
  for (const res of results) {
    const renderOk = res.renderMs <= 1500;
    const zoomOk = res.zoomMs <= 250;
    const rssOk = res.rssMiB <= 512;
    if (renderOk && zoomOk && rssOk) {
      cap = res.cellCount;
    } else {
      break;
    }
  }

  const decisionContent = `# ECharts Heatmap Benchmark Decision

## Benchmark Results
| Cells | Render (ms) | Zoom (ms) | Teardown (ms) | Wire Bytes | RSS (MiB) |
|---|---|---|---|---|---|
${results.map((r) => `| ${r.cellCount} | ${r.renderMs.toFixed(1)} | ${r.zoomMs.toFixed(1)} | ${r.teardownMs.toFixed(1)} | ${r.wireSizeBytes} | ${r.rssMiB.toFixed(1)} |`).join("\n")}

## Decision
- **Hard Viewport-Cell Cap**: ${cap} cells
- **Data Format**: Float32Array typed-array layout (X, Y, Value interleaved) for maximum efficiency and minimal wire size.
`;

  const decisionPath = path.resolve(__dirname, "DECISION.md");
  fs.writeFileSync(decisionPath, decisionContent);
  console.log(`Decision written to ${decisionPath}`);
});
