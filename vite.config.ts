import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const host = process.env.TAURI_DEV_HOST || false

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    host: host || '0.0.0.0',
    hmr: host
      ? {
          protocol: 'ws',
          host,
          port: 5183,
        }
      : undefined,
    watch: {
      // Don't watch src-tauri or android build artifacts to prevent infinite reload loops
      ignored: ['**/src-tauri/**', '**/Backend/**'],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
