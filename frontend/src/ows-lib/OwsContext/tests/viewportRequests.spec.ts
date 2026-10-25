import { describe, expect, it } from 'vitest';

import { Operation } from '../types';
import {
  prepareViewportGetFeatureUrl,
  WFS_VIEWER_FEATURE_LIMIT,
} from '../utils';

const getFeature = (href: string): Operation => ({
  code: 'GetFeature',
  method: 'GET',
  href,
  type: 'application/json',
});

const imported = 'https://example.org/wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature'
  + '&TYPENAME=ns%3Abuildings&SRSNAME=urn%3Aogc%3Adef%3Acrs%3AEPSG%3A%3A25832'
  + '&OUTPUTFORMAT=application%2Fgeo%2Bjson';

describe('the bounded GetFeature request of one viewport', () => {
  it('keeps the negotiated version, request and type name exact', () => {
    const url = prepareViewportGetFeatureUrl(
      getFeature(imported), 'application/geo+json', [0, 0, 10, 10]);

    expect(url.searchParams.get('SERVICE')).toBe('WFS');
    expect(url.searchParams.get('VERSION')).toBe('2.0.0');
    expect(url.searchParams.get('REQUEST')).toBe('GetFeature');
    expect(url.searchParams.get('TYPENAME')).toBe('ns:buildings');
  });

  it('replaces the coordinate reference system with EPSG:4326 and bounds the response', () => {
    const url = prepareViewportGetFeatureUrl(
      getFeature(imported), 'application/geo+json', [1.0, 2.0, 3.0, 4.0]);

    expect(url.searchParams.get('SRSNAME')).toBe('EPSG:4326');
    // the WFS axis order EPSG:4326 is stated in: south,west,north,east with the CRS appended
    expect(url.searchParams.get('BBOX')).toBe('2,1,4,3,EPSG:4326');
    expect(url.searchParams.get('COUNT')).toBe(String(WFS_VIEWER_FEATURE_LIMIT));
    expect(url.searchParams.get('MAXFEATURES')).toBeNull();
  });

  it('uses the count parameter the advertised version names', () => {
    const url = prepareViewportGetFeatureUrl(
      getFeature('https://example.org/wfs?VERSION=1.1.0&TYPENAME=a'), 'json', [0, 0, 1, 1]);

    expect(url.searchParams.get('MAXFEATURES')).toBe(String(WFS_VIEWER_FEATURE_LIMIT));
    expect(url.searchParams.get('COUNT')).toBeNull();
  });

  it('asks for exactly one of the negotiated formats, never a merged list', () => {
    const url = prepareViewportGetFeatureUrl(
      getFeature(imported), 'application/json', [0, 0, 1, 1]);

    expect(url.searchParams.getAll('OUTPUTFORMAT')).toEqual(['application/json']);
  });
});
