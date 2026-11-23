import { expect } from "@playwright/test";
import { createBdd } from "playwright-bdd";

import { test } from "../support/fixtures";
import type { E2EWorld } from "../support/world";
import { resolveNamedValue } from "../support/namedValues";
import { expectBackgroundProcessState } from "../support/waiters";

// The Then category of the step grammar (#1688). A Then either observes the UI
// (through the adapter, never through a selector) or asserts an API invariant
// (through the response log of the world, never through a re-request). The
// asynchronous shape carries its interval and deadline in code.

const { Then } = createBdd(test);

const expectRecordsReadBack = async (world: E2EWorld, status: number) => {
  const ids = world.created.flatMap((entry) => entry.ids);
  expect(ids.length, "the scenario created nothing to read back").toBeGreaterThan(0);
  for (const id of ids) {
    const response = await world.request.get(`/api/registry/dataset-metadata/${id}`, {
      headers: { Accept: "application/vnd.api+json" },
    });
    expect(response.status(), `read-back of ${id}`).toBe(status);
  }
};

Then("I should see {string}", async ({ world }, value) => {
  await world.ui.seesText(resolveNamedValue(value));
});

Then("I should not see {string}", async ({ world }, value) => {
  await world.ui.doesNotSeeText(resolveNamedValue(value));
});

Then("the list answers with rows", async ({ world }) => {
  // Shape-aware and non-vacuous (#1689 review, finding 1): the route table says
  // whether this screen renders a datagrid or the explorer result list, so a
  // summary tile, a facet counter or the empty-state card can never stand in for
  // a record.
  const rows = world.ui.listRows(world.screenShape);
  await expect(rows.first(), `${world.currentScreen} renders no list row`).toBeVisible({ timeout: 30_000 });
});

Then("the list shows the record named {string}", async ({ world }, value) => {
  // An unnamed "rows are visible" only proves the list request was answered; a
  // named record proves the seeded row the stack is supposed to have is there.
  // `-` keeps the example at the row assertion, which is the strongest claim a
  // screen without a stable business identity can make.
  if (value === "-") return;
  const text = resolveNamedValue(value);
  const row = world.screenShape === "explorer"
    ? world.ui.explorerRowContaining(text)
    : world.ui.rowContaining(text);
  await expect(row.first(), `${world.currentScreen} has no row carrying "${text}"`).toBeVisible({ timeout: 30_000 });
});

Then("the page title contains {string}", async ({ world }, expected) => {
  expect(await world.ui.pageTitle()).toContain(expected);
});

Then("every API call of the scenario is answered below 400", async ({ world }) => {
  world.expectNoRejectedApiCalls();
});

Then("no error alert appears", async ({ world }) => {
  await world.ui.expectsNoAlertMatching(/forbidden|not found|error|server communication/i);
});

Then("the error alert names {string}", async ({ world }, text) => {
  await world.ui.seesAlert(resolveNamedValue(text));
});

Then("a file is offered for download", async ({ world }) => {
  expect(world.lastExport ?? "", "the export step offered no download").not.toBe("");
});

Then("the write is refused", async ({ world }) => {
  // JSON:API answers a refused write with errors[].code; the UI renders the same
  // reason. Either proves the refusal — a silent 2xx would not.
  const rejected = world.responses.filter((entry) => entry.status >= 400);
  expect(rejected.map((entry) => `${entry.method} ${entry.url} -> ${entry.status}`), "no request was refused").not.toHaveLength(0);
});

Then("the {word} background process reaches {word}", async ({ world }, processType, state) => {
  await expectBackgroundProcessState(world, processType, state);
});

Then("the record still exists", async ({ world }) => {
  await expectRecordsReadBack(world, 200);
});

Then("the record is gone", async ({ world }) => {
  await expectRecordsReadBack(world, 404);
});

Then("a {word} request matching {string} is answered below 400", async ({ world }, method, pattern) => {
  const matching = world.lastResponsesFor(new RegExp(pattern)).filter((entry) => entry.method === method.toUpperCase());
  expect(matching.length, `no ${method.toUpperCase()} request matching ${pattern} was recorded`).toBeGreaterThan(0);
  for (const entry of matching) expect(entry.status, `${entry.method} ${entry.url}`).toBeLessThan(400);
});
