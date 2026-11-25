import { expect } from "@playwright/test";
import { createBdd, defineParameterType } from "playwright-bdd";

import { test } from "../support/fixtures";
import { resolveFormValue } from "../support/formValues";
import { resolveNamedValue } from "../support/namedValues";
import { SCREEN_NAMES, screenPath } from "../support/paths";

// The When category of the step grammar (#1688). Exactly one action per step,
// because an action with a different expected outcome belongs in a different
// scenario (rule R5: one mutation per scenario). A mutation is done over the API
// unless the mutation itself is what the UI is tested for — that exception is
// spelled out in the contract, not left to a reader's judgement.

const { When } = createBdd(test);

// The screen names a feature file may use, as a cucumber parameter type built
// from the same table the resolver reads. A step written with {word} would match
// "I open the wms list screen" too, and cucumber-expressions then refuses the
// ambiguity at load time; an enumerated type cannot overlap with {word}.
defineParameterType({
  name: "screen",
  // "the dataset list" reads with a space, the table keys it with an underscore.
  regexp: new RegExp(`(?:${[...SCREEN_NAMES].sort((a, b) => b.length - a.length).join("|")})`.replace(/_/g, "[\\s_]")),
});

When("I open the {screen} screen", async ({ world }, screen) => {
  world.resetResponses();
  await world.ui.goto(screenPath(screen));
});

When("I open the list of {word}", async ({ world }, resource) => {
  world.resetResponses();
  await world.ui.goto(`/${resource}`);
});

When("I open the path {string}", async ({ world }, path) => {
  world.resetResponses();
  await world.ui.goto(path);
});

When("I search for {string}", async ({ world }, value) => {
  await world.ui.field("Search").fill(resolveFormValue(resolveNamedValue(value)));
});

When("I expand the results of {word}", async ({ world }, group) => {
  await world.ui.expandGroup(group);
});

When("I sort by {word} {word}", async ({ world }, field, direction) => {
  await world.ui.clickButton(`sort by ${field}`);
  const flip = direction.toLowerCase() === "descending" ? `${field} descending` : `${field} ascending`;
  await world.page.getByRole("menuitem", { name: new RegExp(flip, "i") }).first().click();
});

When("I add the filter {string}", async ({ world }, filter) => {
  await world.ui.clickButton("ADD FILTER");
  await world.page.getByRole("option", { name: filter, exact: false }).first().click();
});

When("I export the current view", async ({ world }) => {
  const download = world.page.waitForEvent("download", { timeout: 30_000 });
  await world.ui.clickButton("EXPORT");
  const file = await download;
  world.lastExport = file.suggestedFilename();
  // the stream has to be consumed, or the download of the response body never finishes
  (await file.createReadStream()).resume();
});

When("I refresh the page", async ({ world }) => {
  world.resetResponses();
  await world.page.reload({ waitUntil: "domcontentloaded" });
});

When("I open the create form of {word}", async ({ world }, resource) => {
  world.resetResponses();
  await world.ui.goto(`/${resource}/create`);
});

When("I fill the form field {string} with {string}", async ({ world }, label, value) => {
  await world.ui.field(label).fill(resolveFormValue(value));
});

When("I choose {string} for the form field {string}", async ({ world }, option, label) => {
  await world.ui.selectOption(label, option);
});

When("I submit the form", async ({ world }) => {
  world.resetResponses();
  await world.ui.submitForm();
});

When("I call the endpoint {string} with {word}", async ({ world }, path, method) => {
  world.resetResponses();
  const response = await world.request.fetch(path, { method: method.toUpperCase(), headers: { Accept: "application/vnd.api+json" } });
  expect(response.status(), `${method.toUpperCase()} ${path}`).toBeLessThan(400);
});

When("I log out", async ({ world }) => {
  await world.ui.logout();
});
