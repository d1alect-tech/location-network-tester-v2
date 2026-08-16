import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  base: '/static/v2/',
  build: {
    outDir: resolve(__dirname, '../src/lnt/ui/static/v2'),
    emptyOutDir: true,
    manifest: true,
    modulePreload: {
      polyfill: false, // Disable modulePreload polyfill to avoid inline scripts
    },
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
      output: {
        entryFileNames: 'assets/[name].[hash].js',
        chunkFileNames: 'assets/[name].[hash].js',
        assetFileNames: 'assets/[name].[hash].[ext]',
      },
    },
  },
  server: {
    port: 9999,
  },
});