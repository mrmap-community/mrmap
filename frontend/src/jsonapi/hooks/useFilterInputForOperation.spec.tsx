import { describe, expect, it } from 'vitest';

import de from '../../i18n/de';
import en from '../../i18n/en';
import { getFilterInputDefinitions, humaniseFilterName } from './useFilterInputForOperation';

// the live schema answers filter parameters without any x-jsonapi-* extension
// when the backend cannot resolve the lookup against the model (issue #945)
const bareParameter = (name: string) => ({
  name: `filter[${name}]`,
  in: 'query',
  schema: { type: 'boolean' },
});

// a filter parameter as the schema answers the ones that carry the extensions
const extendedParameter = (name: string, lookupLabel: string) => ({
  name: `filter[${name}]`,
  in: 'query',
  schema: { type: 'string' },
  'x-jsonapi-field-parts': [name],
  'x-jsonapi-filter-lookup-expression-label': lookupLabel,
});

// mimics the app's i18nProvider: known keys win, everything else falls back
const messages: Record<string, string> = {
  'filterFields.bbox_lat_lon__intersects': 'Bounding box intersects',
};
const translate = (key: string, options?: { _: string }) => messages[key] ?? options?._ ?? key;

describe('humaniseFilterName', () => {
  it('renders snake_case and lookup names as words', () => {
    expect(humaniseFilterName('has_coverage')).toBe('Has coverage');
    expect(humaniseFilterName('bbox_lat_lon__intersects')).toBe('Bbox lat lon intersects');
    expect(humaniseFilterName('harvested_dataset_metadata_relation__harvesting_job'))
      .toBe('Harvested dataset metadata relation harvesting job');
  });

  it('splits camelCase and keeps readable names unchanged', () => {
    expect(humaniseFilterName('boundingGeometry')).toBe('Bounding Geometry');
    expect(humaniseFilterName('title')).toBe('Title');
  });

  it('undoes the source mangling of relation paths', () => {
    expect(humaniseFilterName('a_filter_lookup_b__c')).toBe('A b c');
  });

  it('never ends up empty', () => {
    expect(humaniseFilterName('__')).toBe('__');
  });
});

describe('getFilterInputDefinitions', () => {
  it('keeps the lookup expression label of documented filters', () => {
    const definition = getFilterInputDefinitions(
      extendedParameter('abstract', 'is exactly') as never,
      'DatasetMetadataRecord',
      translate,
    );
    expect(definition?.props.label).toBe('abstract is exactly');
    expect(definition?.props.helperText).toBeUndefined();
  });

  it('renders a human label and no "(undefined)" for filters without schema metadata', () => {
    for (const name of [
      'has_coverage',
      'has_insufficient_quality',
      'has_licence',
      'harvested_dataset_metadata_relation__harvesting_job',
      'bbox_lat_lon__intersects',
    ]) {
      const definition = getFilterInputDefinitions(bareParameter(name) as never, 'DatasetMetadataRecord');
      const label = definition?.props.label as string;
      expect(label).toBeTruthy();
      expect(label).not.toContain('undefined');
      // no raw database lookup syntax is shown to the user
      expect(label).not.toContain('__');
      expect(definition?.props.helperText).toBeUndefined();
    }
  });

  it('prefers the filterFields translation and keeps the humanised name as fallback', () => {
    const translated = getFilterInputDefinitions(
      bareParameter('bbox_lat_lon__intersects') as never,
      'WebMapService',
      translate,
    );
    expect(translated?.props.label).toBe('Bounding box intersects');

    const unknown = getFilterInputDefinitions(
      bareParameter('has_future_feature') as never,
      'WebMapService',
      translate,
    );
    const label = unknown?.props.label as string;
    expect(label).toBe('Has future feature');
    // the translation key must never leak into the UI
    expect(label).not.toContain('filterFields');
  });

  it('shows the description as a parenthesized suffix and as helper text', () => {
    const definition = getFilterInputDefinitions(
      { ...bareParameter('some_date'), description: 'filter by date' } as never,
      'DatasetMetadataRecord',
      translate,
    );
    expect(definition?.props.label).toBe('Some date (filter by date)');
    expect(definition?.props.helperText).toBe('filter by date');
  });
});

describe('filterFields translations', () => {
  // the fields the frontend-walk audit listed as untranslatable (#945); every
  // one needs a non-empty label in both languages of the app
  const auditedFilterNames = [
    'has_coverage',
    'has_insufficient_quality',
    'has_licence',
    'harvested_dataset_metadata_relation__harvesting_job',
    'bbox_lat_lon__intersects',
    'bbox_lat_lon__contains',
    'bbox_lat_lon__covers',
    'bbox_lat_lon__equals',
  ];

  for (const name of auditedFilterNames) {
    it(`labels ${name} in english and german`, () => {
      // de.ts types its message tree loosely (TranslationMessages index signature),
      // so the coverage check reads both label maps as plain string records
      const english = (en.filterFields as unknown as Record<string, string | undefined>)[name];
      const german = ((de as unknown as Record<string, unknown>).filterFields as Record<string, string | undefined> | undefined)?.[name];
      expect(english).toBeTruthy();
      expect(german).toBeTruthy();
      expect(english).not.toContain('undefined');
      expect(german).not.toContain('undefined');
    });
  }
});
