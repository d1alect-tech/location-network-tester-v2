import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const staticV2Dir = path.resolve(__dirname, '../../src/lnt/ui/static/v2');
const manifestPath = path.join(staticV2Dir, '.vite/manifest.json');

function checkBuild() {
  console.log('Running build:check...');

  // 1. Verify manifest exists
  if (!fs.existsSync(manifestPath)) {
    console.error(`Error: Manifest not found at ${manifestPath}`);
    process.exit(1);
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  
  // 2. Verify files in manifest exist on disk
  for (const key of Object.keys(manifest)) {
    const entry = manifest[key];
    const file = entry.file;
    const filePath = path.join(staticV2Dir, file);
    if (!fs.existsSync(filePath)) {
      console.error(`Error: File ${file} from manifest does not exist on disk at ${filePath}`);
      process.exit(1);
    }

    // Check CSS files if any
    if (entry.css) {
      for (const cssFile of entry.css) {
        const cssPath = path.join(staticV2Dir, cssFile);
        if (!fs.existsSync(cssPath)) {
          console.error(`Error: CSS file ${cssFile} from manifest does not exist on disk at ${cssPath}`);
          process.exit(1);
        }
      }
    }
  }

  // 3. Assert no echarts or plotly in product bundle
  const assetsDir = path.join(staticV2Dir, 'assets');
  if (fs.existsSync(assetsDir)) {
    const files = fs.readdirSync(assetsDir);
    for (const file of files) {
      if (file.endsWith('.js')) {
        const content = fs.readFileSync(path.join(assetsDir, file), 'utf-8');
        if (content.includes('echarts') || content.includes('plotly')) {
          console.error(`Error: Product bundle ${file} contains forbidden library string (echarts/plotly)`);
          process.exit(1);
        }
      }
    }
  }

  console.log('build:check PASSED successfully.');
}

checkBuild();
