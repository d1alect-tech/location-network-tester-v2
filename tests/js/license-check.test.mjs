import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const gate = fileURLToPath(new URL("../../frontend/scripts/licenses-check.js", import.meta.url));
const frontend = fileURLToPath(new URL("../../frontend/", import.meta.url));
const approved = {
  echarts: { version: "5.6.0", license: "Apache-2.0" },
  zrender: { version: "5.6.1", license: "BSD-3-Clause" },
  uplot: { version: "1.6.32", license: "MIT" },
  tslib: { version: "2.3.0", license: "0BSD" },
};

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "lnt-license-check-"));
  mkdirSync(path.join(root, "scripts"));
  copyFileSync(gate, path.join(root, "scripts", "licenses-check.js"));
  writeFileSync(
    path.join(root, "package.json"),
    JSON.stringify({ type: "module", dependencies: { echarts: "^5.6.0", uplot: "^1.6.31" } }),
  );
  for (const [name, metadata] of Object.entries(approved)) {
    const packageDir = path.join(root, "node_modules", name);
    mkdirSync(packageDir, { recursive: true });
    writeFileSync(path.join(packageDir, "package.json"), JSON.stringify({ name, ...metadata }));
  }
  return root;
}

function run(root) {
  return spawnSync(process.execPath, [path.join(root, "scripts", "licenses-check.js")], {
    encoding: "utf8",
  });
}

test("license gate accepts the approved shipped runtime set", (t) => {
  const root = fixture();
  t.after(() => rmSync(root, { recursive: true, force: true }));

  const result = run(root);

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /licenses:check PASSED/);
});

test("offline notices include the complete ECharts d3 subcomponent license", () => {
  const notices = readFileSync(path.join(frontend, "public", "third-party-licenses.txt"), "utf8");
  const d3License = readFileSync(
    path.join(frontend, "node_modules", "echarts", "licenses", "LICENSE-d3"),
    "utf8",
  ).trim();

  assert.equal(notices.includes(d3License), true);
});

test("license gate rejects an unapproved production dependency", (t) => {
  const root = fixture();
  t.after(() => rmSync(root, { recursive: true, force: true }));
  writeFileSync(
    path.join(root, "package.json"),
    JSON.stringify({ type: "module", dependencies: { echarts: "^5.6.0", unknown: "1.0.0" } }),
  );

  const result = run(root);

  assert.equal(result.status, 1);
  assert.match(result.stderr, /unapproved production dependency: unknown/);
});

test("license gate rejects missing or changed license metadata", (t) => {
  const root = fixture();
  t.after(() => rmSync(root, { recursive: true, force: true }));
  writeFileSync(
    path.join(root, "node_modules", "echarts", "package.json"),
    JSON.stringify({ name: "echarts", version: "5.6.0" }),
  );

  let result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /echarts.*license: undefined/);

  writeFileSync(
    path.join(root, "node_modules", "echarts", "package.json"),
    JSON.stringify({ name: "echarts", version: "5.6.0", license: "GPL-3.0" }),
  );
  result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /echarts.*license: GPL-3.0/);

  writeFileSync(
    path.join(root, "node_modules", "echarts", "package.json"),
    JSON.stringify({ name: "echarts", version: "5.7.0", license: "Apache-2.0" }),
  );
  result = run(root);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /echarts.*version 5.7.0/);
});

test("license gate rejects missing package metadata", (t) => {
  const root = fixture();
  t.after(() => rmSync(root, { recursive: true, force: true }));
  rmSync(path.join(root, "node_modules", "zrender", "package.json"));

  const result = run(root);

  assert.equal(result.status, 1);
  assert.match(result.stderr, /Package.json.*zrender.*not found/);
});
