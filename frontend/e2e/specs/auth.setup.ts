import { expect, test } from '@playwright/test';

import { login } from '../helpers/session';

test('authenticated state for the acceptance run', async ({ page }) => {
  await login(page);
  await expect(page).not.toHaveURL(/\/login/);
  // One full boot with the fresh cookies: the session cookie itself is set
  // by the request that creates the session row, so the storage state is
  // only complete once a reload has authenticated against the backend.
  await page.reload();
  await page.waitForResponse((r) => r.url().includes('/api/auth/session') && r.status() === 200, { timeout: 30_000 });
  await page.context().storageState({ path: '.output/state.json' });
});
