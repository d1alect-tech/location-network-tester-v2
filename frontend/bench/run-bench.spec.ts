import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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

  const context = page.context();
  const client = await context.newCDPSession(page);
  await client.send("Performance.enable");

  for (const count of cellCounts) {
    console.log(`Running benchmark for ${count} cells...`);

    const result = await page.evaluate(async (c) => {
      return await (window as unknown as WindowWithBenchmark).runBenchmark!(c);
    }, count);

    // Get JS Heap metrics from CDP session
    const performanceMetrics = await client.send("Performance.getMetrics");
    const metricsMap: Record<string, number> = {};
    for (const m of performanceMetrics.metrics) {
      metricsMap[m.name] = m.value;
    }
    const heapUsedMiB = (metricsMap.JSHeapUsedSize || 0) / (1024 * 1024);
    const heapTotalMiB = (metricsMap.JSHeapTotalSize || 0) / (1024 * 1024);

    // Measure real process RSS via PowerShell
    let browserRssMiB = 0;
    try {
      // Run PowerShell to find chrome.exe or chrome-headless-shell.exe processes under ms-playwright and sum WorkingSetSize
      const psCommand =
        "powershell -NoProfile -Command \"(Get-CimInstance Win32_Process -Filter '(Name = ''chrome.exe'' or Name = ''chrome-headless-shell.exe'') and ExecutablePath like ''%ms-playwright%''').WorkingSetSize | Measure-Object -Sum | Select-Object -ExpandProperty Sum\"";
      const output = execSync(psCommand, { encoding: "utf-8" }).trim();
      const totalWorkingSetBytes = Number.parseInt(output, 10) || 0;
      browserRssMiB = totalWorkingSetBytes / (1024 * 1024);
    } catch (err) {
      console.error("Failed to measure process RSS via PowerShell:", err);
    }

    results.push({
      ...result,
      heapUsedMiB,
      heapTotalMiB,
      browserRssMiB,
    });
  }

  console.log("Benchmark Results:", results);

  // Write fresh measurements to a TEMP file: routine runs must not clobber the
  // committed snapshot (noisy RSS would rewrite it on every e2e run).
  const resultsPath = path.join(os.tmpdir(), "lnt-bench-results.json");
  const resultsWithHost = {
    host: {
      os: "Windows 10 Home 22H2 x64",
      cpu: "Ryzen 7 7800X3D",
      ram: "31.6 GiB",
    },
    rss_method:
      "Sum of WorkingSetSize of chrome.exe processes containing 'ms-playwright' in ExecutablePath via PowerShell Get-CimInstance Win32_Process",
    results,
  };
  fs.writeFileSync(resultsPath, `${JSON.stringify(resultsWithHost, null, 2)}\n`);
  console.log(`Results written to ${resultsPath}`);

  // Determine the hard viewport-cell cap and data format
  // Budgets: <= 1.5s render, <= 250ms interaction (zoom), <= 512MiB RSS
  let cap = 64000;
  for (const res of results) {
    const renderOk = res.renderMs <= 1500;
    const zoomOk = res.zoomMs <= 250;
    const rssOk = res.browserRssMiB <= 512;
    if (renderOk && zoomOk && rssOk) {
      cap = res.cellCount;
    } else {
      break;
    }
  }

  // The finalized decision is frozen (todo 37): never rewrite it. Recompute the
  // cap and report loudly when it drifts from the committed DECISION.md.
  const committedDecision = fs.readFileSync(path.resolve(__dirname, "DECISION.md"), "utf-8");
  const match = /Hard Viewport-Cell Cap\*\*: (\d+) cells/.exec(committedDecision);
  const committedCap = match === null ? null : Number(match[1]);
  if (committedCap !== cap) {
    console.warn(
      `[bench] recomputed cap ${cap} differs from finalized cap ${committedCap} — DECISION.md left untouched`,
    );
  } else {
    console.log(`[bench] recomputed cap matches finalized cap (${cap} cells)`);
  }
});
