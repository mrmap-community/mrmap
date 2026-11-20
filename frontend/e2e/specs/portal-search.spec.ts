import { expect, test, type Page } from '@playwright/test';

import {
  DATASET_TITLE_ABSENT,
  DATASET_TITLE_EMPTY,
  DATASET_TITLE_VALID,
  SEARCH_TERM,
  WMS_TITLE
} from '../helpers/fixtures';
import { expectNoForbiddenAlert } from '../helpers/session';

// Issue #1034 - the final browser acceptance of the #948 frontend walk.
// The original failure: /search resolved the absent operation
// `list_DatasetMetadata` and answered every load with the alert
// "Operation 'list_DatasetMetadata' not found." while EXPORT failed with
// "Server communication error". The page must now ask
// `list_DatasetMetadataRecord` (the operation the schema really has) and
// show dataset and WMS results side by side.
//
// The chromium project carries the authenticated storage state (auth.setup),
// so every navigation here is one app boot, not a re-login.

type ApiCall = { url: string, status: number };

const collectApi = (page: Page): ApiCall[] => {
  const calls: ApiCall[] = [];
  page.on('response', (response) => {
    if (response.url().includes('/api/')) {
      calls.push({ url: response.url(), status: response.status() });
    }
  });
  return calls;
};

const sawCall = (calls: ApiCall[], pattern: RegExp) =>
  calls.some((call) => pattern.test(call.url) && call.status < 400);

test.describe('/search - portal search page (#1034)', () => {

  test('loads dataset and WMS results without an error alert', async ({ page }) => {
    const calls = collectApi(page);
    await page.goto('/search');

    // the request that names the operation: list_DatasetMetadataRecord is
    // the /api/registry/dataset-metadata route of the generated schema
    await expect
      .poll(() => sawCall(calls, /\/api\/registry\/dataset-metadata\?.*filter%5Bsearch%5D/),
        { message: 'the dataset list request of the search page' })
      .toBe(true);
    await expect
      .poll(() => sawCall(calls, /\/api\/registry\/wms\?.*filter%5Bis_update_candidate%5D=false/),
        { message: 'the WMS list request of the search page' })
      .toBe(true);
    expect(calls.filter((call) => call.status >= 400), 'every API call answers below 400').toEqual([]);
    await expectNoForbiddenAlert(page);
  });

  test('the dataset and WMS accordions list the seeded records, search and refresh keep them', async ({ page }) => {
    const calls = collectApi(page);
    await page.goto('/search');

    await page.getByRole('button', { name: 'DatasetMetadataRecord', exact: true }).click();
    await expect(page.getByText(DATASET_TITLE_VALID)).toBeVisible();
    await expect(page.getByText(DATASET_TITLE_EMPTY)).toBeVisible();
    await expect(page.getByText(DATASET_TITLE_ABSENT)).toBeVisible();

    await page.getByRole('button', { name: 'WebMapService', exact: true }).click();
    await expect(page.getByText(WMS_TITLE, { exact: true }).first()).toBeVisible();

    // search: the filter of the form reaches the dataset list
    await page.getByLabel('Search', { exact: true }).fill(SEARCH_TERM);
    await expect
      .poll(() => sawCall(calls, new RegExp(`/api/registry/dataset-metadata\\?.*filter%5Bsearch%5D=${SEARCH_TERM}`)),
        { message: 'the search term reaches the dataset list request' })
      .toBe(true);
    await expect(page.getByText(DATASET_TITLE_VALID)).toBeVisible();
    await expect(page.getByText(DATASET_TITLE_EMPTY)).not.toBeVisible();

    // refresh: clearing the term returns every record again
    await page.getByLabel('Search', { exact: true }).fill('');
    await expect(page.getByText(DATASET_TITLE_EMPTY)).toBeVisible();
    await expectNoForbiddenAlert(page);
  });

  test('the generated schema names list_DatasetMetadataRecord and has no list_DatasetMetadata', async ({ request }) => {
    const response = await request.get('/api/schema', { headers: { Accept: 'application/json' } });
    expect(response.ok()).toBeTruthy();
    const schema = await response.text();
    expect(schema).toContain('"list_DatasetMetadataRecord"');
    expect(schema).not.toContain('"list_DatasetMetadata"');
  });

  test('export works where it is offered: the dataset list EXPORT downloads', async ({ page }) => {
    await page.goto('/DatasetMetadataRecord');
    await expect(page.getByText(DATASET_TITLE_VALID)).toBeVisible({ timeout: 30_000 });
    const download = page.waitForEvent('download', { timeout: 20_000 });
    await page.getByRole('button', { name: 'EXPORT' }).click();
    const file = await download;
    expect(file.suggestedFilename().length).toBeGreaterThan(0);
    await expectNoForbiddenAlert(page);
  });
});
