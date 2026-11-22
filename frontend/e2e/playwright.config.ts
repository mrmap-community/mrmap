import { defineConfig, devices } from '@playwright/test';
import { defineBddProject } from 'playwright-bdd';

// Browser acceptance harness for the BUILT SPA served by nginx — the same
// image the production compose files build (docker/nginx/nginx.Dockerfile),
// never the Vite development server (issue #1034). It runs inside the
// mcr.microsoft.com/playwright image; see README.md for the exact stack and
// runner commands.
//
// One runner for both layers (#1689): the Gherkin scenarios generated into
// .features-gen and the plain specs of #1034 are two projects of THIS config,
// so one `playwright test` invocation runs both against the same stack with
// the same browsers, the same login state and the same artifact settings.
// `defineBddProject` is not a second Playwright runtime — it only returns the
// testDir of the generated files, which this config runs like any other project.

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:18085';

export default defineConfig({
  testDir: './specs',
  outputDir: '.output',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: '.output/results.json' }],
    // Cucumber-compatible feed of the Gherkin scenarios (#1689): the JSON is
    // what external BDD tooling consumes, the HTML is the readable report.
    ['playwright-bdd/reporter/cucumber', { type: 'json', outputFile: '.output/cucumber.json' }],
    ['playwright-bdd/reporter/cucumber', { type: 'html', outputFile: '.output/cucumber.html' }]
  ],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off'
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      // generated from features/*.feature by `bddgen`; shares the login state
      // of the setup project, because storageState lives in the root `use`
      ...defineBddProject({
        name: 'bdd',
        featuresRoot: 'features',
        features: 'features/**/*.feature',
        steps: ['steps/**/*.ts'],
        // one fixture set for both layers: the steps and the generated tests share
        // the test object of support/fixtures.ts
        importTestFrom: 'support/fixtures.ts'
      }),
      dependencies: ['setup']
    },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: '.output/state.json' },
      dependencies: ['setup']
    }
  ]
});
