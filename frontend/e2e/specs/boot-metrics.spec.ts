import { expect, test } from '@playwright/test';

import { writeFile } from 'node:fs/promises';

// Issue #946 - the boot must not ship the megabytes of the OpenAPI schema and
// of the bundle uncompressed, and a later load must not transfer them over
// the wire again. This spec measures with the browser's own network data and
// records the numbers as evidence; it asserts the two qualitative facts the
// issue names (compression present, no unnecessary refetch) and invents no
// thresholds - a LAN stack and the original demo deployment are not the same
// environment.

type Measured = {
  url: string,
  status: number,
  contentEncoding: string,
  wireBytes: number,
  decodedBytes: number
};

const LARGE_PAYLOAD = /\/api\/schema|\/assets\/index-[^/]+\.js$/;

const measure = (page: import('@playwright/test').Page): Measured[] => {
  const entries: Measured[] = [];
  page.on('response', async (response) => {
    const url = response.url();
    if (!LARGE_PAYLOAD.test(url)) return;
    const sizes = await response.request().sizes();
    let decoded = sizes.responseBodySize;
    try {
      decoded = (await response.body()).length;
    } catch {
      // an answer without a body keeps the wire size as its measure
    }
    entries.push({
      // the origin is stripped, not substituted: the stack publishes any
      // free host port (see README), so the spec must not assume one
      url: url.replace(/^\w+:\/\/[^/]+/, ''),
      status: response.status(),
      contentEncoding: response.headers()['content-encoding'] ?? 'identity',
      wireBytes: sizes.responseBodySize,
      decodedBytes: decoded
    });
  });
  return entries;
};

test.describe('cold and warm boot (#946)', () => {

  test('large payloads arrive compressed and never retransferred', async ({ page }) => {
    const cold = measure(page);

    // cold boot: the first document load of this context has no body cache;
    // the authenticated storage state rides along on this very request
    await page.goto('/');
    const schemaResponse = await page.waitForResponse((r) => r.url().includes('/api/schema'), { timeout: 30_000 });
    expect(schemaResponse.status()).toBe(200);
    await expect(page.getByText('Dashboard').first()).toBeVisible({ timeout: 30_000 });
    const schemaLoads = cold.filter((entry) => entry.url.startsWith('/api/schema'));
    const bundleLoads = cold.filter((entry) => entry.url.startsWith('/assets/'));
    expect(schemaLoads.length, 'the schema is fetched once per boot').toBe(1);
    expect(bundleLoads.length, 'the main bundle is fetched once per boot').toBe(1);
    for (const entry of [...schemaLoads, ...bundleLoads]) {
      expect(entry.contentEncoding, `content-encoding of ${entry.url}`).toBe('gzip');
      expect(entry.wireBytes, `wire size of ${entry.url} stays below its decoded size`)
        .toBeLessThan(entry.decodedBytes);
    }

    // warm load: a hard navigation to a deep link - the large payloads must
    // not come over the wire again as fresh 200 bodies
    const warm = measure(page);
    await page.goto('/DatasetMetadataRecord');
    await expect(page.getByRole('button', { name: 'EXPORT' })).toBeVisible({ timeout: 30_000 });
    const retransferred = warm.filter((entry) => entry.status === 200 && entry.wireBytes > 1024);

    const evidence = {
      note: 'measured inside the isolated acceptance stack (nginx + built SPA, local network, dev-overlay backend); not comparable to the original audit deployment',
      cold: [...schemaLoads, ...bundleLoads],
      warmHardNavigationOverWire: retransferred
    };
    await writeFile('.output/boot-metrics.json', JSON.stringify(evidence, null, 2));
    console.log('#946 boot evidence:', JSON.stringify(evidence, null, 2));
    expect(retransferred, 'the warm load retransfers no large payload as a fresh 200').toEqual([]);
  });
});
