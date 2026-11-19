import { expect, test, type Page } from '@playwright/test';

import { DATASET_TITLE_ABSENT, DATASET_TITLE_VALID } from '../helpers/fixtures';
import { expectNoForbiddenAlert } from '../helpers/session';

// Issues #943, #944, #945 and #1035 - the sort contract of the lists, the
// schema documentation of the `sort` parameter, and the filter labels.
// The authenticated storage state of the chromium project is used directly.

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

test.describe('lists and their sort contract (#943, #1035)', () => {

  test('the Language list renders rows, sorts and exports (#943)', async ({ page }) => {
    const calls = collectApi(page);
    await page.goto('/Language');
    // #943's symptom was an empty page without any error: rows prove the
    // list request the page sends is answered
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 30_000 });
    await expect
      .poll(() => sawCall(calls, /\/api\/registry\/languages\?.*sort=/),
        { message: 'a sorted language list request' })
      .toBe(true);
    expect(calls.filter((call) => call.status >= 400), 'every API call answers below 400').toEqual([]);

    const download = page.waitForEvent('download', { timeout: 20_000 });
    await page.getByRole('button', { name: 'EXPORT' }).click();
    const file = await download;
    expect(file.suggestedFilename().length).toBeGreaterThan(0);
    await expectNoForbiddenAlert(page);
  });

  test('the keyword list loads without the #1035 rejection', async ({ page }) => {
    const calls = collectApi(page);
    await page.goto('/Keyword');
    await expect
      .poll(() => sawCall(calls, /\/api\/registry\/keywords\?.*sort=/),
        { message: 'the keyword list asks with a sort and is answered' })
      .toBe(true);
    const rejected = calls.filter((call) => call.url.includes('/keywords') && call.status >= 400);
    expect(rejected, 'no keyword query answers 4xx/5xx').toEqual([]);
    await expectNoForbiddenAlert(page);
  });

  test('the failed background processes view loads without its alert (#1035)', async ({ page }) => {
    const calls = collectApi(page);
    await page.goto('/BackgroundProcess?filter=%7B%22status%22%3A%22failed%22%7D');
    await expect
      .poll(() => sawCall(calls, /\/api\/notify\/background-processes\?.*sort=/),
        { message: 'the background process query is answered' })
      .toBe(true);
    const rejected = calls.filter((call) => call.url.includes('background-processes') && call.status >= 400);
    expect(rejected, 'no background-process query 4xx/5xx').toEqual([]);
    await expectNoForbiddenAlert(page);
  });

  test('exercising a documented sort: dataset records by title, ascending then descending (#944)', async ({ page }) => {
    const calls = collectApi(page);
    await page.goto('/DatasetMetadataRecord');
    await expect(page.getByText(DATASET_TITLE_VALID)).toBeVisible({ timeout: 30_000 });

    // the cards follow the DOM order; the shipped default is title ascending,
    // so the "E2E ..." row leads the page
    const order = () => page.evaluate((titles: string[]) => {
      const text = document.body.innerText;
      return titles.map((title) => text.indexOf(title));
    }, [DATASET_TITLE_ABSENT, DATASET_TITLE_VALID]);
    expect((await order())[0], 'ascending: E2E row before Niederschlag row').toBeLessThan((await order())[1]);

    await page.getByRole('button', { name: /sort by title/i }).click();
    // the SortButton menu answers with the field's directions; the shipped
    // default is ascending, so the flip is the DESCENDING entry
    await page.getByRole('menuitem', { name: /title descending/i }).click();
    await expect
      .poll(() => sawCall(calls, /\/api\/registry\/dataset-metadata\?.*sort=-title/),
        { message: 'the flip asks the API for title descending' })
      .toBe(true);
    await expect
      .poll(async () => (await order())[0] > (await order())[1],
        { message: 'descending: E2E row after Niederschlag row' })
      .toBe(true);
  });
});

test.describe('the schema documents its sort parameters (#944)', () => {

  test('every paginated list endpoint of /api/schema declares sort', async ({ request }) => {
    const response = await request.get('/api/schema', { headers: { Accept: 'application/json' } });
    expect(response.ok()).toBeTruthy();
    const schema = await response.json() as {
      paths: Record<string, Record<string, { parameters?: { name?: string }[] }>>
    };
    let paginated = 0;
    const undocumented: string[] = [];
    for (const [path, operations] of Object.entries(schema.paths)) {
      const list = operations.get;
      if (!list) continue;
      const names = new Set((list.parameters ?? []).map((parameter) => parameter.name));
      if (names.has('page[number]') || names.has('page[size]')) {
        paginated += 1;
        if (!names.has('sort')) undocumented.push(path);
      }
    }
    // the original audit counted 87, the schema of current develop has more;
    // the gate is: none without a documented sort
    expect(paginated).toBeGreaterThan(80);
    expect(undocumented, 'paginated endpoints without a documented sort').toEqual([]);
  });
});

test.describe('filter labels (#945)', () => {

  test('ADD FILTER offers human labels, no literal undefined, bbox included', async ({ page }) => {
    await page.goto('/DatasetMetadataRecord');
    await page.getByRole('button', { name: 'ADD FILTER' }).click();
    // the bbox facet of the original table must carry its human label
    await expect(page.getByText('boundingGeometry intersects').first()).toBeVisible({ timeout: 15_000 });
    const text = await page.evaluate(() => document.body.innerText);
    expect(text, 'no filter label renders the literal (undefined)').not.toMatch(/\(undefined\)/);
    expect(text).toContain('Has geographic coverage');
    expect(text).toContain('Has licence');
  });
});
