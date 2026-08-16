import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const packageJsonPath = path.resolve(__dirname, '../package.json');
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));

console.log('Running licenses:check...');

// We only care about production dependencies
const prodDeps = Object.keys(packageJson.dependencies || {});

// uPlot is MIT. Let's verify all production dependencies are MIT or other allowed licenses.
// Since uPlot is the only production dependency, we can check its license.
for (const dep of prodDeps) {
  const depPackageJsonPath = path.resolve(__dirname, `../node_modules/${dep}/package.json`);
  if (!fs.existsSync(depPackageJsonPath)) {
    console.error(`Error: Package.json for production dependency ${dep} not found at ${depPackageJsonPath}`);
    process.exit(1);
  }
  const depPackageJson = JSON.parse(fs.readFileSync(depPackageJsonPath, 'utf-8'));
  const license = depPackageJson.license;
  if (license !== 'MIT') {
    console.error(`Error: Production dependency ${dep} has unclassified/unallowed license: ${license}`);
    process.exit(1);
  }
  console.log(`Dependency ${dep}: ${license} (OK)`);
}

console.log('licenses:check PASSED successfully.');
