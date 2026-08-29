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
        showcaseRound2Index: resolve(__dirname, 'showcase-round2.html'),
        showcaseRound2V1: resolve(__dirname, 'showcase-v1.html'),
        showcaseRound2V2: resolve(__dirname, 'showcase-v2.html'),
        showcaseRound2V3: resolve(__dirname, 'showcase-v3.html'),
        showcaseRound2V4: resolve(__dirname, 'showcase-v4.html'),
        showcaseRound2V5: resolve(__dirname, 'showcase-v5.html'),
        showcaseRound2V6: resolve(__dirname, 'showcase-v6.html'),
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