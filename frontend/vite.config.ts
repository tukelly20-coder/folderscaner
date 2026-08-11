import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/scanner/',
  plugins: [react()],
  server: {
    port: 8001,
    proxy: {
      '/scanner-api': {
        target: 'http://127.0.0.1:18001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/scanner-api/, '/api'),
      },
      '/scanner-ws': {
        target: 'ws://127.0.0.1:18001',
        ws: true,
        rewrite: (path) => path.replace(/^\/scanner-ws/, '/ws'),
      },
    },
  },
});
