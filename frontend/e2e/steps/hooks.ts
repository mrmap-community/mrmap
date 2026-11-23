import { createBdd } from "playwright-bdd";

import { test } from "../support/fixtures";

// Hooks of the Gherkin layer (#1688, "No hidden seeding").
//
// Nothing here seeds data: the stack is seeded deterministically before the run
// (acceptance_seed.py), and a scenario that needs its own row creates it through
// a step that names it.
//
// Artifact redaction is NOT here. An `AfterAll` of this kind is worker-scoped: it
// fires after the last scenario of the worker, before the reporters write their
// files, and a throw in it is not necessarily red. The redaction of the run now
// lives in support/artifactReporter.ts, which runs once after the run and can
// turn the run red (#1689 review, finding 3).

const { Before } = createBdd(test);

// Every scenario starts with an empty response log: the API assertions of a
// scenario only see the calls that scenario made.
Before(async ({ world }) => {
  world.resetResponses();
});
