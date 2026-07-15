import { defineConfig } from '@playwright/test'

const PORT = 8799
const TOKEN = 'e2e-test-token'
const BASE = `http://127.0.0.1:${PORT}`

process.env.WORKBENCH_URL ??= `${BASE}/#token=${TOKEN}`

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  use: { baseURL: BASE },
  webServer: {
    // Requires scripts/build_frontend.py first so the static UI is bundled.
    command: `python -m data_workbench.cli --port ${PORT} --no-browser --token ${TOKEN}`,
    url: `${BASE}/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
