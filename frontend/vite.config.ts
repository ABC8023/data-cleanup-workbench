/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    globals: true,
    // Playwright specs under e2e/ run via `playwright test`, not vitest.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
