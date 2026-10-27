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
    strictPort: true,
    host: host || '127.0.0.1',
    hmr: host
      ? {
          protocol: 'ws',
          host,
          port: 5183,
        }
      : undefined,
    watch: {
      // Backend and Tauri write runtime data while the frontend is open.
      // SQLite WAL/SHM changes on each mic session must not reload the page
      // and interrupt capture.
      ignored: [
        '**/src-tauri/**',
        '**/Backend/**',
        '**/Data/**',
        '**/*.sqlite',
        '**/*.sqlite-*',
        '**/*.sqlite3',
        '**/*.sqlite3-*',
        '**/*.db-wal',
        '**/*.db-shm',
      ],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
