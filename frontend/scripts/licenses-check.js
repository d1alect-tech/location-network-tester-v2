import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const packageJsonPath = path.resolve(__dirname, "../package.json");
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf-8"));

console.log("Running licenses:check...");

// We only care about production dependencies
const prodDeps = Object.keys(packageJson.dependencies || {});

const approvedRuntime = {
  echarts: { version: "5.6.0", license: "Apache-2.0" },
  zrender: { version: "5.6.1", license: "BSD-3-Clause" },
  uplot: { version: "1.6.32", license: "MIT" },
  tslib: { version: "2.3.0", license: "0BSD" },
};

for (const dep of prodDeps) {
  if (!Object.hasOwn(approvedRuntime, dep)) {
    console.error(`Error: unapproved production dependency: ${dep}`);
    process.exit(1);
  }
}

for (const [dep, approved] of Object.entries(approvedRuntime)) {
  const depPackageJsonPath = path.resolve(__dirname, `../node_modules/${dep}/package.json`);
  if (!fs.existsSync(depPackageJsonPath)) {
    console.error(
      `Error: Package.json for production dependency ${dep} not found at ${depPackageJsonPath}`,
    );
    process.exit(1);
  }
  const depPackageJson = JSON.parse(fs.readFileSync(depPackageJsonPath, "utf-8"));
  if (depPackageJson.version !== approved.version || depPackageJson.license !== approved.license) {
    console.error(
      `Error: Production dependency ${dep} has unapproved metadata: version ${depPackageJson.version}, license: ${depPackageJson.license}`,
    );
    process.exit(1);
  }
  console.log(`Dependency ${dep}@${approved.version}: ${approved.license} (OK)`);
}

console.log("licenses:check PASSED successfully.");
