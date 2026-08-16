import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const frontendDir = path.resolve(__dirname, '..');
const staticV2Dir = path.resolve(__dirname, '../../src/lnt/ui/static/v2');

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

function generateManifest() {
  console.log('Generating build-manifest.json...');

  // 1. Source inputs
  const sourceFiles = [
    path.join(frontendDir, 'index.html'),
    path.join(frontendDir, 'vite.config.ts'),
    path.join(frontendDir, 'package-lock.json'),
    ...getFilesRecursive(path.join(frontendDir, 'src'))
  ];

  const sources = {};
  for (const file of sourceFiles) {
    if (fs.existsSync(file)) {
      const relativePath = path.relative(frontendDir, file).replace(/\\/g, '/');
      sources[relativePath] = computeFileHash(file);
    }
  }

  // 2. Emitted outputs
  const outputFiles = getFilesRecursive(staticV2Dir);
  const outputs = {};
  for (const file of outputFiles) {
    const relativePath = path.relative(staticV2Dir, file).replace(/\\/g, '/');
    if (relativePath !== '.vite/build-manifest.json') {
      outputs[relativePath] = computeFileHash(file);
    }
  }

  const manifest = {
    sources,
    outputs
  };

  const manifestDir = path.join(staticV2Dir, '.vite');
  if (!fs.existsSync(manifestDir)) {
    fs.mkdirSync(manifestDir, { recursive: true });
  }

  fs.writeFileSync(
    path.join(manifestDir, 'build-manifest.json'),
    JSON.stringify(manifest, null, 2),
    'utf-8'
  );

  console.log('build-manifest.json generated successfully.');
}

generateManifest();
