import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  // klinecharts is only reached through the lazy-loaded ChartPanel; pre-bundle it at dev
  // startup so opening the price-chart panel doesn't trigger a mid-session dep re-optimize
  // (which blanks the chart until a manual reload).
  optimizeDeps: {
    include: ['klinecharts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
