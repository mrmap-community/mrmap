import { AfterAll, Before, createBdd } from "playwright-bdd";

import { redactArtifacts } from "../support/redaction";

// Hooks of the Gherkin layer (#1688, "Artifact redaction" + "No hidden seeding").
// Nothing here seeds data: the stack is seeded deterministically before the run,
// and a scenario that needs its own row creates it through a step that names it.
//
// AfterAll is worker-scoped, so it fires after the last scenario of the worker;
// it scrubs the JSON artifacts of the run (storage states, request bodies) and
// reports what it removed. Trace files are zip archives and belong to the
// tracer (#1698), which redacts them before the artifact is uploaded.

createBdd().AfterAll(async () => {
  const dir = process.env.E2E_BDD_ARTIFACTS ?? ".output/bdd";
  const { redacted, storageStates } = redactArtifacts(dir);
  if (redacted.length > 0 || storageStates > 0) {
    console.log(`[e2e-bdd] redacted ${redacted.length} artifact file(s), ${storageStates} storage state(s) in ${dir}`);
  }
});

// Every scenario starts with an empty response log: the API assertions of a
// scenario only see the calls that scenario made.
Before(async ({ world }) => {
  world.resetResponses();
});
