import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scripts = fileURLToPath(new URL("../../frontend/scripts/", import.meta.url));

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "lnt-build-public-inputs-"));
  const frontend = path.join(root, "frontend");
  const scriptsDir = path.join(frontend, "scripts");
  mkdirSync(path.join(frontend, "public"), { recursive: true });
  mkdirSync(scriptsDir);
  copyFileSync(path.join(scripts, "build-manifest.js"), path.join(scriptsDir, "build-manifest.js"));
  copyFileSync(path.join(scripts, "build-check.js"), path.join(scriptsDir, "build-check.js"));
  writeFileSync(path.join(frontend, "package.json"), JSON.stringify({ type: "module" }));
  writeFileSync(path.join(frontend, "index.html"), "fixture");
  writeFileSync(path.join(frontend, "vite.config.ts"), "fixture");
  writeFileSync(path.join(frontend, "package-lock.json"), "fixture");
  return { root, frontend };
}

function run(frontend, script) {
  return spawnSync(process.execPath, [path.join(frontend, "scripts", script)], {
    encoding: "utf8",
  });
}

test("build inventory detects changed, new, and removed public files", (t) => {
  const { root, frontend } = fixture();
  const notice = path.join(frontend, "public", "notice.txt");
  const extra = path.join(frontend, "public", "extra.txt");
  t.after(() => rmSync(root, { recursive: true, force: true }));
  writeFileSync(notice, "original");

  assert.equal(run(frontend, "build-manifest.js").status, 0);
  assert.equal(run(frontend, "build-check.js").status, 0);

  writeFileSync(notice, "changed");
  let result = run(frontend, "build-check.js");
  assert.equal(result.status, 1);
  assert.match(result.stderr, /public\/notice\.txt has drifted/);

  assert.equal(run(frontend, "build-manifest.js").status, 0);
  writeFileSync(extra, "new");
  result = run(frontend, "build-check.js");
  assert.equal(result.status, 1);
  assert.match(result.stderr, /New source file public\/extra\.txt/);

  assert.equal(run(frontend, "build-manifest.js").status, 0);
  rmSync(notice);
  result = run(frontend, "build-check.js");
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Source file public\/notice\.txt.*missing on disk/);
});
