import { expect, test, type Page } from '@playwright/test';

import {
  DATASET_ABSENT_GEOMETRY_PK,
  DATASET_EMPTY_GEOMETRY_PK,
  DATASET_TITLE_ABSENT,
  DATASET_TITLE_EMPTY,
  DATASET_TITLE_VALID,
  DATASET_VALID_GEOMETRY_PK
} from '../helpers/fixtures';

// Issue #947 - the map cards and the viewer must survive valid, absent and
// malformed geometry without the uncaught "Invalid GeoJSON object." error.
// The pages the original audit names: the dataset list with its MAP view
// (valid, empty and absent geometries side by side), the service explorer
// with SEARCH THIS AREA, and the viewer. The record show pages are walked
// beside them: they render the extent chip instead of a map, and no page of
// this gate may throw the GeoJSON error.

// Collects both faces of the original defect: the console error and the
// uncaught exception behind it.
const watchGeoJsonErrors = (page: Page): string[] => {
  const seen: string[] = [];
  page.on('console', (message) => {
    const text = `${message.text()} ${message.location().url}`;
    if (/invalid geojson/i.test(text)) seen.push(`console: ${text}`);
  });
  page.on('pageerror', (error) => {
    if (/invalid geojson/i.test(String(error))) seen.push(`pageerror: ${String(error)}`);
  });
  return seen;
};

test.describe('record pages over the mixed geometries (#947)', () => {

  for (const [label, pk, title] of [
    ['valid polygon', DATASET_VALID_GEOMETRY_PK, DATASET_TITLE_VALID],
    ['EMPTY geometry', DATASET_EMPTY_GEOMETRY_PK, 'Relative Feuchte'],
    ['absent geometry', DATASET_ABSENT_GEOMETRY_PK, DATASET_TITLE_ABSENT]
  ] as const) {
    test(`the show page of the ${label} record renders without a GeoJSON error`, async ({ page }) => {
      const errors = watchGeoJsonErrors(page);
      await page.goto(`/DatasetMetadataRecord/${pk}/show`);
      await expect(page.getByText(title).first()).toBeVisible({ timeout: 30_000 });
      expect(errors, `no "Invalid GeoJSON" error on the ${label} page`).toEqual([]);
    });
  }

  test('the list names the empty and the absent record honestly', async ({ page }) => {
    const errors = watchGeoJsonErrors(page);
    await page.goto('/DatasetMetadataRecord');
    await expect(page.getByText(DATASET_TITLE_EMPTY)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('No extent recorded').first()).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe('map surfaces over the mixed geometries (#947)', () => {

  test('the list MAP view toggles, zooms and keeps its map usable', async ({ page }) => {
    const errors = watchGeoJsonErrors(page);
    await page.goto('/DatasetMetadataRecord');
    await page.getByRole('button', { name: 'MAP' }).click();
    await expect(page.locator('.leaflet-container').first()).toBeVisible({ timeout: 30_000 });
    await page.locator('.leaflet-control-zoom-in').first().click();
    await page.locator('.leaflet-control-zoom-in').first().click();
    await page.locator('.leaflet-control-zoom-out').first().click();
    // the coverage legend of the mixed records - the usable map the issue asks for
    await expect(page.getByText(/datasets on this page/i).first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('the service explorer keeps its map over SEARCH THIS AREA', async ({ page }) => {
    const errors = watchGeoJsonErrors(page);
    await page.goto('/service-explorer');
    await expect(page.locator('.leaflet-container').first()).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: 'SEARCH THIS AREA' }).click();
    await page.waitForTimeout(4000);
    // the area query must not throw the layer away
    await expect(page.locator('.leaflet-container').first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('the viewer boots a usable map', async ({ page }) => {
    const errors = watchGeoJsonErrors(page);
    await page.goto('/viewer');
    await expect(page.locator('.leaflet-container').first()).toBeVisible({ timeout: 30_000 });
    // adding services through the catalogues is the discovery epic #669's
    // subject - this gate only asks that the viewer itself stays usable
    expect(errors).toEqual([]);
  });
});
