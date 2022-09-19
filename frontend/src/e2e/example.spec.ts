import { expect, test } from '@playwright/test';

test('basic test', async ({ page }) => {
  await page.goto('/');

  const [response] = await Promise.all([
    page.waitForResponse(/api\/schema/, {
      timeout: 30000,
    }),
  ]);

  expect(response.status()).toBe(200);

  const desc = page.locator('.ant-pro-form-login-desc');
  await expect(desc).toHaveText('Spatial Service Registry');
});
