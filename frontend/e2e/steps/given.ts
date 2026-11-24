import { createBdd } from "playwright-bdd";

import { test, CREDENTIALS } from "../support/fixtures";
import { resolveNamedValue } from "../support/namedValues";

// The Given category of the step grammar (#1688). A Given only establishes a
// precondition: nothing here submits a form, because a mutation belongs to When
// (rule R4). The secret of a role never travels through a feature file — the
// step names a *role* and the secret is read from the stack's environment.

const { Given } = createBdd(test);

const SESSION_KEYS = ["authorization", "username", "rememberUser"];

const basic = (role: string) => {
  const credential = CREDENTIALS[role as keyof typeof CREDENTIALS];
  if (!credential) throw new Error(`unknown role "${role}" — known: ${Object.keys(CREDENTIALS).join(", ")}`);
  return Buffer.from(`${credential.username}:${credential.secret}`).toString("base64");
};

Given("the acceptance stack answers", async ({ world }) => {
  const response = await world.request.get("/api/schema", { headers: { Accept: "application/json" } });
  if (!response.ok()) throw new Error(`/api/schema answered ${response.status()} — the stack is not up`);
});

Given("I am authenticated as {word} through the API", async ({ world, page }, role) => {
  // the browser session of the SPA (#835) — the same endpoint the login page
  // uses, so the scenario navigates authenticated without typing a credential
  // into a form.
  const response = await world.request.post("/api/auth/session", {
    headers: { Authorization: `Basic ${basic(role)}`, Accept: "application/json" },
  });
  if (!response.ok()) throw new Error(`session for role "${role}" answered ${response.status()}`);
  // the storage state of the chromium project already carries an admin session;
  // a scenario that names its role owns its session, so drop the inherited one.
  await page.evaluate((keys: string[]) => keys.forEach((key) => localStorage.removeItem(key)), SESSION_KEYS);
  world.rememberToken(role, "session-cookie");
});

Given("the {word} role has a token", async ({ world }, role) => {
  // the machine path of #835, which is what the cross-role matrix of #1687 uses.
  const response = await world.request.post("/api/auth/login", {
    headers: { Authorization: `Basic ${basic(role)}`, Accept: "application/json" },
  });
  if (!response.ok()) throw new Error(`token for role "${role}" answered ${response.status()}`);
  const body = (await response.json()) as { token?: string };
  if (!body.token) throw new Error(`the login of role "${role}" answered without a token`);
  world.rememberToken(role, body.token);
});

Given("I am an anonymous user", async ({ page }) => {
  await page.evaluate((keys: string[]) => keys.forEach((key) => localStorage.removeItem(key)), SESSION_KEYS);
});

Given("the seed data is visible to me", async ({ world }) => {
  const response = await world.request.get("/api/registry/dataset-metadata?page[size]=5", {
    headers: { Accept: "application/vnd.api+json" },
  });
  if (!response.ok()) throw new Error(`the seeded dataset list answered ${response.status()}`);
});

Given("the title of the seeded {word} is known to me", async (_fixtures, kind) => {
  // a step that returned a pk here would violate R3; it resolves the *display
  // value*, which is what a feature file is allowed to name.
  resolveNamedValue(kind.toLowerCase() === "wms" ? "{seed.wms.title}" : "{seed.dataset.title}");
});
