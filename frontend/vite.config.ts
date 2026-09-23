import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Development uses Vite as the browser-facing origin and proxies the Server API.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', 'VITE_')

  return {
    envDir: '..',
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: env.VITE_DEV_SERVER_TARGET ?? 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
