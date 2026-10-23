import type { Offering, OWSResourceProperties } from './types';

import { describe, expect, it } from 'vitest';

import { getRenderableGetMapOperation, getUnsupportedReasons, isRenderableResource, isRequestedByActivation } from './capabilities';
import { OWSContext, OWSResource } from './core';
import { validateOwsContext, WMS_OFFERING_CODE } from './validation';

const WMTS_OFFERING_CODE = 'http://www.opengis.net/spec/owc-geojson/1.0/req/wmts';

const resource = (
  offerings: Offering[],
  properties: Partial<OWSResourceProperties> = {},
) => new OWSResource({
  title: 'resource',
  updated: '2026-01-01T00:00:00Z',
  folder: '/0',
  offerings,
  ...properties,
} as OWSResourceProperties);

const wmsGetMap = (method = 'GET', active = true) => ({
  code: WMS_OFFERING_CODE,
  operations: [
    { code: 'GetMap', method, href: 'https://example.org/wms?LAYERS=a', active },
  ],
});

describe('resource capabilities', () => {
  it('names the GetMap a viewer can render and nothing else about that resource', () => {
    const renderable = resource([wmsGetMap(), {
      code: WMTS_OFFERING_CODE,
      operations: [{ code: 'GetTile', method: 'GET', href: 'https://example.org/wmts' }],
    }]);

    expect(getRenderableGetMapOperation(renderable)?.method).toBe('GET');
    // the supported alternative is resolved explicitly: it outranks everything else
    expect(getUnsupportedReasons(renderable)).toEqual([]);
    expect(isRenderableResource(renderable)).toBe(true);
  });

  it('names an unsupported offering and its contents while the resource stays kept as an extension', () => {
    const wmts = resource([{
      code: WMTS_OFFERING_CODE,
      operations: [{ code: 'GetTile', method: 'GET', href: 'https://example.org/wmts' }],
      contents: [{ type: 'application/geopackage+sqlite3', href: 'https://example.org/a.gpkg' }],
    }]);

    expect(getUnsupportedReasons(wmts)).toEqual([
      { kind: 'offering', code: WMTS_OFFERING_CODE },
      { kind: 'content', type: 'application/geopackage+sqlite3' },
    ]);
  });

  it('names a GetMap offered as POST instead of executing it in silence', () => {
    const postOnly = resource([wmsGetMap('POST')]);

    expect(isRenderableResource(postOnly)).toBe(false);
    expect(getUnsupportedReasons(postOnly)).toEqual([
      { kind: 'method', code: 'GetMap', method: 'POST' },
    ]);
  });

  it('names the missing GetMap of an offering which asks for more than it can deliver', () => {
    const queryable = resource([{
      code: WMS_OFFERING_CODE,
      operations: [{ code: 'GetFeatureInfo', method: 'GET', href: 'https://example.org/wms?', active: true }],
    }]);

    expect(getUnsupportedReasons(queryable)).toEqual([{ kind: 'operation', code: 'GetMap' }]);
  });

  it('names nothing about a resource which asks for nothing, e.g. a plain group node', () => {
    expect(getUnsupportedReasons(resource([]))).toEqual([]);
  });

  it('reads the request for rendering from the activation of the resource itself', () => {
    const activatedOperation = resource([wmsGetMap('POST')]);
    activatedOperation.getWmsOperationByCode('GetMap')!.active = true;
    expect(isRequestedByActivation(activatedOperation)).toBe(true);

    const activatedWithoutOperation = resource([{ code: WMTS_OFFERING_CODE }], { active: true });
    expect(isRequestedByActivation(activatedWithoutOperation)).toBe(true);

    const keptInactive = resource([wmsGetMap('POST', false)], { active: false });
    expect(isRequestedByActivation(keptInactive)).toBe(false);
  });
});

const mixedDocument = () => ({
  type: 'FeatureCollection',
  id: 'urn:uuid:6e8bc430-9c3a-01d9-a7b7-0800200c9a66',
  bbox: [-180, -90, 180, 90],
  properties: {
    lang: 'en',
    title: 'mixed document',
    updated: '2026-01-01T00:00:00Z',
    links: { profiles: ['http://www.opengis.net/spec/owc-geojson/1.0/req/core'] },
  },
  features: [
    {
      type: 'Feature',
      id: 'supported',
      properties: {
        title: 'supported', updated: '2026-01-01T00:00:00Z', folder: '/0',
        offerings: [wmsGetMap()],
      },
    },
    {
      type: 'Feature',
      id: 'post only',
      properties: {
        title: 'post only', updated: '2026-01-01T00:00:00Z', folder: '/1', active: true,
        offerings: [wmsGetMap('POST')],
      },
    },
    {
      type: 'Feature',
      id: 'wmts',
      properties: {
        title: 'wmts', updated: '2026-01-01T00:00:00Z', folder: '/2', active: true,
        offerings: [{
          code: WMTS_OFFERING_CODE,
          operations: [{ code: 'GetTile', method: 'GET', href: 'https://example.org/wmts' }],
          contents: [{ type: 'application/geopackage+sqlite3', href: 'https://example.org/a.gpkg' }],
        }],
      },
    },
  ],
});

describe('mixed supported and unsupported documents', () => {
  it('are importable and keep every unsupported member through the viewer round trip', () => {
    const imported = validateOwsContext(mixedDocument());
    expect(imported.hasErrors).toBe(false);
    const context = OWSContext.fromPlainObject(imported.context!);

    // a JSON round trip is what copying, editing and reimporting the document goes through
    const reimported = validateOwsContext(JSON.parse(JSON.stringify(context)));
    expect(reimported.hasErrors).toBe(false);

    const offeringsOf = (
      features: { properties: { title: string; offerings?: unknown[] } }[],
      title: string,
    ) => features.find(feature => feature.properties.title === title)?.properties.offerings;
    const roundTripped = reimported.context!.features;
    expect(offeringsOf(roundTripped, 'post only'))
      .toEqual(offeringsOf(imported.context!.features, 'post only'));
    expect(offeringsOf(roundTripped, 'wmts'))
      .toEqual(offeringsOf(imported.context!.features, 'wmts'));
    expect(JSON.stringify(offeringsOf(roundTripped, 'wmts'))).toContain(WMTS_OFFERING_CODE);
  });

  it('report exactly the unsupported resources the request building skips', () => {
    const context = OWSContext.fromPlainObject(validateOwsContext(mixedDocument()).context!);

    const requested = context.features.filter(feature =>
      getUnsupportedReasons(feature).length > 0 && isRequestedByActivation(feature));
    expect(requested.map(feature => feature.id)).toEqual(['post only', 'wmts']);

    // the supported resource keeps its renderable request untouched, the way the viewer filters
    expect(context.getOptimizedUrlsByCode('GetMap',
      feature => feature.getWmsOperationByCode('GetMap')?.active === true)
      .flatMap(request => request.features.map(feature => feature.id))).toEqual(['supported']);
  });
});
