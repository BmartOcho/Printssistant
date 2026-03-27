import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  root: 'frontend',
  build: {
    outDir: '../static',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index:            resolve(__dirname, 'frontend/index.html'),
        preflight:        resolve(__dirname, 'frontend/preflight.html'),
        profile:          resolve(__dirname, 'frontend/profile.html'),
        'suggest-idea':   resolve(__dirname, 'frontend/suggest-idea.html'),
        'forgot-password':resolve(__dirname, 'frontend/forgot-password.html'),
        'reset-password': resolve(__dirname, 'frontend/reset-password.html'),
      },
    },
  },
})
