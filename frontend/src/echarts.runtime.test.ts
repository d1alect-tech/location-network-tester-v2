/** W2: echarts is a runtime heatmap dependency (offline = no CDN, not no echarts). */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { TILE_CELL_CAP } from "./components/charts/spectrogramModel";

const PACKAGE_JSON = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../package.json");

describe("echarts runtime dependency and spectrogram cap", () => {
  it("lists echarts ^5.6.0 in dependencies, not devDependencies", () => {
    const pkg = JSON.parse(fs.readFileSync(PACKAGE_JSON, "utf8")) as {
      dependencies?: { echarts?: string };
      devDependencies?: { echarts?: string };
    };
    expect(pkg.dependencies?.echarts).toBe("^5.6.0");
    expect(pkg.devDependencies?.echarts).toBeUndefined();
  });

  it("keeps the client tile cap at 524000 cells", () => {
    expect(TILE_CELL_CAP).toBe(524_000);
  });
});
