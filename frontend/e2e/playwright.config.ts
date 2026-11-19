import { defineConfig, devices } from '@playwright/test';

// Browser acceptance harness for the BUILT SPA served by nginx — the same
// image the production compose files build (docker/nginx/nginx.Dockerfile),
// never the Vite development server (issue #1034). It runs inside the
// mcr.microsoft.com/playwright image; see README.md for the exact stack and
// runner commands.

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:18085';

export default defineConfig({
  testDir: './specs',
  outputDir: '.output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: '.output/results.json' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off'
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: '.output/state.json' },
      dependencies: ['setup']
    }
  ]
});
