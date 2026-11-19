import { expect, test } from '@playwright/test';

import { CSW_PK, DATASET_VALID_GEOMETRY_PK } from '../helpers/fixtures';

// Issues #941, #942 and #1036 - deep links, the asset 404, and the SPA routes
// whose name starts with a proxied prefix. All of these run ANONYMOUS: the
// question is whether the built SPA boots at all behind nginx, which needs
// no session (the boot ends on the login page, not on "Loading…" forever).

test.use({ storageState: { cookies: [], origins: [] } });

const DEEP_LINKS = [
  `/DatasetMetadataRecord/${DATASET_VALID_GEOMETRY_PK}`,
  `/DatasetMetadataRecord/${DATASET_VALID_GEOMETRY_PK}/show`,
  '/DatasetMetadataRecord/create',
  '/WebMapService/create',
  `/CatalogueService/${CSW_PK}/show/HarvestingJob`,
  '/BackgroundProcess/1/show'
] as const;

test.describe('deep links boot the SPA (#941)', () => {

  for (const path of DEEP_LINKS) {
    test(`hard navigation to ${path} boots the app`, async ({ page }) => {
      const assetResponses: { url: string, status: number, contentType: string }[] = [];
      page.on('response', (response) => {
        const contentType = response.headers()['content-type'] ?? '';
        if (response.url().includes('/assets/')) {
          assetResponses.push({ url: response.url(), status: response.status(), contentType });
        }
      });
      const response = await page.goto(path);
      expect(response?.status(), `${path} answers at the edge`).toBe(200);
      // the booted app of an anonymous browser is the login form - reaching
      // it proves the bundle parsed and the router ran; "Loading…" forever
      // was the original symptom
      await expect(page.getByLabel(/user ?name/i).first()).toBeVisible({ timeout: 30_000 });
      // every asset the boot fetched resolved with its own content type,
      // never as the SPA fallback's text/html
      expect(assetResponses.length, 'the boot loaded hashed assets').toBeGreaterThan(0);
      for (const asset of assetResponses) {
        expect(asset.status, `asset ${asset.url}`).toBe(200);
        expect(asset.contentType, `content type of ${asset.url}`).not.toContain('text/html');
      }
    });
  }

  test('/csw-client reaches the SPA, not Django (#1036)', async ({ page }) => {
    const response = await page.goto('/csw-client');
    expect(response?.status(), '/csw-client is an SPA route, not a proxied 404').toBe(200);
    expect(response?.headers()['content-type']).toContain('text/html');
    await expect(page.getByLabel(/user ?name/i).first()).toBeVisible({ timeout: 30_000 });
  });
});

test.describe('missing static assets answer 404 (#942)', () => {

  test('a missing hashed bundle is a 404, not the cached SPA shell', async ({ request }) => {
    for (const path of ['/assets/index-DEADBEEFDEADBEEF.js', '/definitely-not-here.png']) {
      const missing = await request.get(path);
      expect(missing.status(), `${path} answers 404 at the edge`).toBe(404);
      // the original failure answered 200 with the app shell, cacheable as
      // if it were real; the shell must not come back under a 404 either
      expect(await missing.text(), `${path} is not the SPA shell`).not.toContain('id="root"');
    }
  });

  test('the real bundle of the index is served with its own content type', async ({ request }) => {
    const shell = await request.get('/');
    const shellText = await shell.text();
    const match = /src="(\/assets\/index-[^"]+\.js)"/.exec(shellText);
    expect(match, 'the served index.html names its bundle at an absolute /assets url (#941)').not.toBeNull();
    const asset = await request.get(match![1]);
    expect(asset.status()).toBe(200);
    expect(asset.headers()['content-type']).toMatch(/javascript/);
  });
});
