import { defineConfig, devices } from '@playwright/test';
import { cucumberReporter, defineBddProject } from 'playwright-bdd';

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
    // Two things the reporter wrapper of `playwright-bdd` insists on:
    // - the built-in reporter is named via `cucumberReporter()` — the adapter
    //   reads it from `$type`, a plain { type: ... } makes it treat "undefined"
    //   as a custom reporter path and die in onEnd;
    // - the files must live OUTSIDE `outputDir`: the wrapper opens its stream
    //   while the reporters are constructed, and Playwright wipes `.output/`
    //   when the run starts, so anything written there before the run is gone.
    cucumberReporter('json', { outputFile: 'cucumber-report/cucumber.json' }),
    cucumberReporter('html', { outputFile: 'cucumber-report/cucumber.html' }),
    // Last, so the JSON report above is on disk when the artifacts are scrubbed
    // and the login state removed. A throw in its onEnd turns the run red, which
    // is what makes the redaction of #1688 an assertion and not a comment
    // (#1689 review, finding 3).
    ['./support/artifactReporter.ts']
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
      // generated from features/*.feature by `bddgen`; shares the login state of
      // the setup project the same way the chromium project does, via its own
      // `use.storageState`.
      ...defineBddProject({
        name: 'bdd',
        featuresRoot: 'features',
        features: 'features/**/*.feature',
        // v9 dropped importTestFrom: the module that exports the extended test
        // object must be part of the `steps` pattern itself, so the generated
        // files import their fixture from it. That is also what makes one fixture
        // set serve both layers — the plain specs import the same module.
        steps: ['support/fixtures.ts', 'steps/**/*.ts']
      }),
      // defineBddProject only returns { name, testDir }, so the login state of
      // the setup project has to be set here too: without it every scenario
      // boots on /login and a step waits for a field that is never rendered.
      use: { ...devices['Desktop Chrome'], storageState: '.output/state.json' },
      dependencies: ['setup']
    },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: '.output/state.json' },
      dependencies: ['setup']
    }
  ]
});
