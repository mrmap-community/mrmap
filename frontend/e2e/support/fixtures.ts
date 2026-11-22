import { test as base } from "@playwright/test";

import { E2EWorld } from "./world";

// One place where the acceptance identities exist (#1688). The credentials come
// from the environment of the stack, never from a feature file; the feature file
// names a *role*.
//
// This module is also the unit test surface of the systemtest layer itself:
// the step library is tested against it, which is how the library stays
// mergeable across machines of different speed.

export const CREDENTIALS = {
  admin: {
    username: process.env.E2E_USER ?? "acceptance",
    secret: process.env.E2E_PASS ?? "Acceptance-e2e",
  },
  // The restricted role of the cross-role matrix (#1687). It is provisioned by
  // the acceptance seed; where a stack has no such user, the scenario is skipped
  // through the tag rather than deleted.
  restricted: {
    username: process.env.E2E_RESTRICTED_USER ?? "e2e-restricted",
    secret: process.env.E2E_RESTRICTED_PASS ?? "Restricted-e2e",
  },
} as const;

export type CredentialRole = keyof typeof CREDENTIALS;

export type BddFixtures = { world: E2EWorld };

// The single fixture that hands a step the adapters and the response log.
// playwright-bdd generates one test per scenario, so the world is per scenario.
export const test = base.extend<BddFixtures>({
  world: async ({ page, request }, use) => {
    await use(new E2EWorld(page, request));
  },
});

export { expect } from "@playwright/test";
