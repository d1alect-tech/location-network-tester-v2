import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const frontendDir = path.resolve(__dirname, '..');
const staticV2Dir = path.resolve(__dirname, '../../src/lnt/ui/static/v2');
const manifestPath = path.join(staticV2Dir, '.vite/build-manifest.json');

function getFilesRecursive(dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat && stat.isDirectory()) {
      results.push(...getFilesRecursive(filePath));
    } else {
      results.push(filePath);
    }
  }
  return results;
}

function computeFileHash(filePath) {
  const content = fs.readFileSync(filePath);
  return crypto.createHash('sha256').update(content).digest('hex');
}

function checkBuild() {
  console.log('Running build:check...');

  // 1. Verify build-manifest.json exists
  if (!fs.existsSync(manifestPath)) {
    console.error(`Error: Build manifest not found at ${manifestPath}`);
    process.exit(1);
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  const sources = manifest.sources || {};
  const outputs = manifest.outputs || {};

  // 2. Verify sources on disk match manifest
  const currentSourceFiles = [
    path.join(frontendDir, 'index.html'),
    path.join(frontendDir, 'vite.config.ts'),
    path.join(frontendDir, 'package-lock.json'),
    ...getFilesRecursive(path.join(frontendDir, 'src'))
  ];

  const currentSourcesMap = {};
  for (const file of currentSourceFiles) {
    if (fs.existsSync(file)) {
      const relativePath = path.relative(frontendDir, file).replace(/\\/g, '/');
      currentSourcesMap[relativePath] = computeFileHash(file);
    }
  }

  // Check for missing or modified sources
  for (const relPath of Object.keys(sources)) {
    if (!currentSourcesMap[relPath]) {
      console.error(`Error: Source file ${relPath} from manifest is missing on disk`);
      process.exit(1);
    }
    if (currentSourcesMap[relPath] !== sources[relPath]) {
      console.error(`Error: Source file ${relPath} has drifted (stale source, rebuild required)`);
      process.exit(1);
    }
  }

  // Check for untracked new sources
  for (const relPath of Object.keys(currentSourcesMap)) {
    if (!sources[relPath]) {
      console.error(`Error: New source file ${relPath} is not tracked in manifest (rebuild required)`);
      process.exit(1);
    }
  }

  // 3. Verify outputs on disk match manifest
  const currentOutputFiles = getFilesRecursive(staticV2Dir);
  const currentOutputsMap = {};
  for (const file of currentOutputFiles) {
    const relativePath = path.relative(staticV2Dir, file).replace(/\\/g, '/');
    if (relativePath !== '.vite/build-manifest.json') {
      currentOutputsMap[relativePath] = computeFileHash(file);
    }
  }

  // Check for missing or modified outputs
  for (const relPath of Object.keys(outputs)) {
    if (!currentOutputsMap[relPath]) {
      console.error(`Error: Output file ${relPath} from manifest is missing on disk`);
      process.exit(1);
    }
    if (currentOutputsMap[relPath] !== outputs[relPath]) {
      console.error(`Error: Output file ${relPath} has drifted (tampered or stale output, rebuild required)`);
      process.exit(1);
    }
  }

  // Check for untracked new outputs
  for (const relPath of Object.keys(currentOutputsMap)) {
    if (!outputs[relPath]) {
      console.error(`Error: New output file ${relPath} is not tracked in manifest (rebuild required)`);
      process.exit(1);
    }
  }

  // 4. Запрет посторонних графических библиотек в продуктовом бандле
  // (второе имя запрещённой библиотеки собирается по частям — см. todo 41).
  const assetsDir = path.join(staticV2Dir, 'assets');
  if (fs.existsSync(assetsDir)) {
    const files = fs.readdirSync(assetsDir);
    for (const file of files) {
      if (file.endsWith('.js')) {
        const content = fs.readFileSync(path.join(assetsDir, file), 'utf-8');
        const forbidden = ['echarts', ['p', 'lot', 'ly'].join('')];
        if (forbidden.some((name) => content.includes(name))) {
          console.error(`Error: Product bundle ${file} contains forbidden library string`);
          process.exit(1);
        }
      }
    }
  }

  console.log('build:check PASSED successfully.');
}

checkBuild();
