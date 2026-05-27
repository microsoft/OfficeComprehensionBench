import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Build output goes to ./dist. A GH Actions workflow promotes those files
// to the branch root for GitHub Pages serving.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  publicDir: 'public',
});
