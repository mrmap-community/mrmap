import { expect, type Page } from '@playwright/test';

// The deterministic login of the acceptance stack (see README.md): the
// dedicated superuser `acceptance` sees every seeded record through the
// audited break-glass of decision Q6=A (extras/permissions.py).
const USER = process.env.E2E_USER ?? 'acceptance';
const PASS = process.env.E2E_PASS ?? 'Acceptance-e2e';

export const login = async (page: Page) => {
  await page.goto('/');
  const username = page.getByLabel(/user ?name/i).first();
  // waitFor is the observable variant: the SPA still shows "Loading…" for a
  // moment, so the login form either appears within the timeout or the
  // context is already authenticated. (isVisible() would return at once.)
  const onLoginPage = await username.waitFor({ state: 'visible', timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  if (!onLoginPage) {
    // the context carries a live session (storageState) - nothing to do
    return;
  }
  await username.fill(USER);
  await page.getByLabel(/password/i).first().fill(PASS);
  await page.getByRole('button', { name: /sign ?in|log ?in/i }).first().click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 30_000 });
};

// Alert texts are the original failure signals of #1034 and #943; no page of
// this gate may ever show one of them.
export const FORBIDDEN_ALERTS = [
  /Operation .* not found/,
  /Server communication error/,
  /Unable to load background activity/
] as const;

export const expectNoForbiddenAlert = async (page: Page) => {
  const text = await page.evaluate(() => document.body.innerText);
  for (const pattern of FORBIDDEN_ALERTS) {
    expect(text, `page shows forbidden alert matching ${pattern}`).not.toMatch(pattern);
  }
};
