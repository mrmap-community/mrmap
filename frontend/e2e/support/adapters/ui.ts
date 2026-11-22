import { expect, type Locator, type Page } from "@playwright/test";

// The UI adapter (#1688): the only place of the Gherkin layer that knows how the
// SPA renders. Steps call these methods; a step that reaches for a CSS selector
// is a failed review. When the UI changes, exactly this module changes.
//
// Every locator here is a react-admin contract: role based (`getByRole`) or the
// accessible text of a field label — not a generated class name.

export class UiAdapter {
  constructor(private readonly page: Page) {}

  goto(path: string) {
    return this.page.goto(path);
  }

  /** One of the two list shapes of the app: a table (datagrid) or the card grid of the service screens. */
  listRows(): Locator {
    return this.page.locator("table tbody tr, .MuiCard-root");
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
