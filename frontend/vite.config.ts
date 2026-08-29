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
        showcase: resolve(__dirname, 'showcase.html'),
        showcaseRedesignIndex: resolve(__dirname, 'showcase-redesign.html'),
        showcaseVariantA: resolve(__dirname, 'showcase-a.html'),
        showcaseVariantB: resolve(__dirname, 'showcase-b.html'),
        showcaseVariantC: resolve(__dirname, 'showcase-c.html'),
        showcaseVariantD: resolve(__dirname, 'showcase-d.html'),
      },
      output: {
        entryFileNames: 'assets/[name].[hash].js',
        chunkFileNames: 'assets/[name].[hash].js',
        assetFileNames: 'assets/[name].[hash].[ext]',
      },
    },
  },
  server: {
    port: 4101,
  },
});