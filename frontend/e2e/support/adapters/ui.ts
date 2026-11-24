import { expect, type Locator, type Page } from "@playwright/test";

import type { ListShape } from "../paths";

// The UI adapter (#1688): the only place of the Gherkin layer that knows how the
// SPA renders. Steps call these methods; a step that reaches for a CSS selector
// is a failed review. When the UI changes, exactly this module changes.
//
// Every locator here is a react-admin contract: role based (`getByRole`) or the
// accessible text of a field label — not a generated class name. The two
// exceptions are the documented ones of the #1688 *Selector policy* and name
// themselves at the method: the row selectors of `support/paths.ts` (which the
// list-answer steps of `steps/then.ts` consume), and the result-row anchor the
// metadata explorer itself uses to keep its compact result list and its map
// selection in sync (a DOM contract of the app, not a styling class).

export class UiAdapter {
  constructor(private readonly page: Page) {}

  goto(path: string) {
    return this.page.goto(path);
  }

  /**
   * The rows a list screen renders.
   *
   * The shape comes from the route table (`support/paths.ts`) and is never
   * guessed from what happens to be on screen. A page always renders chrome —
   * summary tiles, facet cards, the empty-state card — so an assertion which
   * accepts "any card-like element" is satisfied on a healthy stack whose list
   * is empty, which #1688 calls a harness bug ("an assertion whose failure no
   * report can show"). Both branches therefore name the row element of their
   * list and nothing else:
   *
   * - `datagrid`: the body rows of the react-admin table, and only of the branch
   *   which holds records. `Datagrid` answers `isPending === true` with
   *   `DatagridLoading`, whose `<tbody>` carries `nbFakeLines = 5` placeholder
   *   rows and, being a bare MUI `TableBody`, none of the datagrid classes;
   *   `DatagridBody` alone adds `DatagridClasses.tbody`. A pending request
   *   therefore renders visible `<tbody><tr>`s which are not a list answer, so
   *   that class is what separates "the backend answered" from "the page started
   *   loading" — the #1688 non-vacuity rule, and the reason a bare
   *   `table tbody tr` is not enough. Nothing in the app sets
   *   `emptyWhileLoading`, so `ListView` does render the datagrid while the
   *   first `useList` of a screen is in flight.
   * - `explorer`: the result rows of the metadata explorer, which `ExplorerView
   *   .tsx` gives `id="dataset-result-<pk>"`. That screen renders no table at
   *   all — it is a result list beside a coverage map — and the only cards on it
   *   are its facet counters, which stay visible with zero results.
   */
  listRows(shape: ListShape): Locator {
    return shape === "explorer" ? this.explorerRows() : this.datagridRows();
  }

  /** Documented exception (list-answer steps): the row selector of a datagrid. */
  datagridRows(): Locator {
    // RaDatagrid-tbody (useDatagridStyles.tsx) is a literal class and exists
    // only on DatagridBody; the loading skeleton of DatagridLoading renders an
    // unclassed <tbody> with five placeholder rows, which must not count as a
    // list answer. rowContaining() inherits this through this method.
    return this.page.locator("tbody.RaDatagrid-tbody > tr");
  }

  /** Documented exception (explorer rows): the app's own result-row anchor. */
  explorerRows(): Locator {
    return this.page.locator("[id^='dataset-result-']");
  }

  /** A datagrid row whose cells carry `text` — the record a scenario names. */
  rowContaining(text: string): Locator {
    return this.datagridRows().filter({ hasText: text });
  }

  /** An explorer result row whose title or abstract carries `text`. */
  explorerRowContaining(text: string): Locator {
    return this.explorerRows().filter({ hasText: text });
  }

  /** A row of the screen's shape whose cells carry `text`. */
  listRowContaining(shape: ListShape, text: string): Locator {
    return shape === "explorer" ? this.explorerRowContaining(text) : this.rowContaining(text);
  }

  field(label: string): Locator {
    return this.page.getByLabel(label, { exact: true }).first();
  }

  async clickButton(name: string) {
    await this.page.getByRole("button", { name, exact: false }).first().click();
  }

  /** One result group of the portal search: the groups are accordions, so a
   *  group answers nothing until its summary is activated. */
  async expandGroup(name: string) {
    await this.page.getByRole("button", { name, exact: true }).click();
  }

  async selectOption(label: string, option: string) {
    await this.field(label).click();
    await this.page.getByRole("option", { name: option, exact: false }).first().click();
  }

  submitForm() {
    return this.clickButton("save");
  }

  text(): Promise<string> {
    return this.page.evaluate(() => document.body.innerText);
  }

  async seesText(text: string) {
    await expect(this.page.getByText(text, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  }

  async doesNotSeeText(text: string) {
    await expect(this.page.getByText(text, { exact: false }).first()).toHaveCount(0);
  }

  /** The form validation error of a field — the error a refused write answers with. */
  async formError(label: string): Promise<string> {
    const error = this.page.getByText(new RegExp(`^${label}`, "i")).locator("xpath=ancestor::*[self::div][1]").locator("p.MuiFormHelperText-root");
    return (await error.first().innerText({ timeout: 10_000 })) ?? "";
  }

  /** The Snackbar/MuiAlert text, which is how the app surfaces "403 Forbidden". */
  async alertText(): Promise<string> {
    const alerts = this.page.locator(".MuiAlert-root");
    if ((await alerts.count()) === 0) return "";
    return (await alerts.allInnerTexts()).join("\n");
  }

  async seesAlert(text: string) {
    await expect(this.page.locator(".MuiAlert-root").filter({ hasText: text }).first()).toBeVisible({ timeout: 30_000 });
  }

  async expectsNoAlertMatching(pattern: RegExp) {
    const offenders = (await this.alertText()).split("\n").filter((line) => pattern.test(line));
    expect(offenders, "no error alert appeared").toEqual([]);
  }

  pageTitle(): Promise<string> {
    return this.page.title();
  }

  currentPath() {
    return new URL(this.page.url()).pathname;
  }

  /** Login through the form — used by the one auth scenario that keeps UI login on purpose. */
  async login(username: string, password: string) {
    await this.page.goto("/login");
    await this.page.getByLabel(/user ?name/i).first().fill(username);
    await this.page.getByLabel(/password/i).first().fill(password);
    await this.page.getByRole("button", { name: /log ?in/i }).first().click();
    await this.page.waitForURL(/\/(dashboard|search|WebMapService|Keyword)/, { timeout: 30_000 });
  }

  async logout() {
    await this.page.request.delete("/api/auth/session");
    await this.page.goto("/login");
  }
}
