import type { Offering, OfferingDimension } from './types';

import { describe, expect, test } from 'vitest';

import { parseWms } from '../XMLParser/parseCapabilities';
import dimensionsCapabilities from '../XMLParser/tests/capabilities_dimensions_130.xml?raw';
import { OWSContext, OWSResource } from './core';
import {
    getDimensionParameter,
    getWmsDimensionSelection,
    isAllowedDimensionValue,
    parseAdvertisedValues,
    setWmsDimension,
} from './dimensions';
import { wmsToOWSResources } from './utils';
import { validateOwsContext, WMS_OFFERING_CODE } from './validation';

const elevation: OfferingDimension = { name: 'elevation', values: '0,10,20', default: '10', units: 'CRS:84' };
const sensor: OfferingDimension = { name: 'DIM_sensor', values: '0/100/10', default: '0' };

const offering = (): Offering => ({
    code: WMS_OFFERING_CODE,
    dimensions: [elevation, sensor],
    operations: [
        { code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a&token=map', active: true },
        { code: 'GetFeatureInfo', method: 'GET', href: 'https://example.org/wms?LAYERS=a&QUERY_LAYERS=a&token=info', active: false },
    ],
});

describe('WMS dimension parameters and advertised values', () => {
    test('derives the request parameter from the advertised name', () => {
        expect(getDimensionParameter('elevation')).toBe('ELEVATION');
        expect(getDimensionParameter('Elevation')).toBe('ELEVATION');
        expect(getDimensionParameter('DIM_sensor')).toBe('DIM_SENSOR');
        expect(getDimensionParameter('dim_sensor')).toBe('DIM_SENSOR');
        expect(getDimensionParameter('depth')).toBe('DIM_DEPTH');
    });

    test('reads value lists and numeric ranges, keeping everything else a list', () => {
        expect(parseAdvertisedValues('0,10,20')).toEqual({ kind: 'list', values: ['0', '10', '20'] });
        expect(parseAdvertisedValues('0/100/10')).toEqual({ kind: 'range', start: 0, stop: 100, step: 10 });
        expect(parseAdvertisedValues('0/100')).toEqual({ kind: 'range', start: 0, stop: 100 });
        expect(parseAdvertisedValues('2000-01-01/2020-01-01/P1D'))
            .toEqual({ kind: 'list', values: ['2000-01-01/2020-01-01/P1D'] });
    });

    test('validates values against the advertised list, range and interval', () => {
        expect(isAllowedDimensionValue(elevation, '20')).toBe(true);
        expect(isAllowedDimensionValue(elevation, '5')).toBe(false);
        expect(isAllowedDimensionValue(elevation, '')).toBe(true);
        expect(isAllowedDimensionValue(sensor, '30')).toBe(true);
        expect(isAllowedDimensionValue(sensor, '35')).toBe(false);
        expect(isAllowedDimensionValue(sensor, '105')).toBe(false);
        expect(isAllowedDimensionValue(sensor, 'chilly')).toBe(false);
    });
});

describe('WMS dimension selection', () => {
    test('writes both operations of the offering and keeps activation, parameters and query subsets', () => {
        const target = offering();
        setWmsDimension(target, 'elevation', '20');
        const [map, info] = target.operations!;
        expect(new URL(map.href).searchParams.get('ELEVATION')).toBe('20');
        expect(new URL(info.href).searchParams.get('ELEVATION')).toBe('20');
        expect(new URL(map.href).searchParams.get('token')).toBe('map');
        expect(new URL(info.href).searchParams.get('QUERY_LAYERS')).toBe('a');
        expect(map.active).toBe(true);
        expect(info.active).toBe(false);
        expect(getWmsDimensionSelection(target, elevation)).toBe('20');
    });

    test('replaces a lower-case import variant and removes the parameter for the server default', () => {
        const target = offering();
        target.operations![0].href = 'https://example.org/wms?LAYERS=a&elevation=5';
        setWmsDimension(target, 'elevation', '10');
        const mapUrl = new URL(target.operations![0].href);
        expect(mapUrl.searchParams.get('ELEVATION')).toBe('10');
        expect([...mapUrl.searchParams.keys()]).not.toContain('elevation');
        setWmsDimension(target, 'elevation', '');
        expect([...new URL(target.operations![0].href).searchParams.keys()])
            .not.toContain('ELEVATION');
    });

    test('refuses values the service does not offer and unknown dimension names', () => {
        const target = offering();
        const before = JSON.stringify(target);
        setWmsDimension(target, 'DIM_sensor', '35');
        setWmsDimension(target, 'depth', '1');
        expect(JSON.stringify(target)).toBe(before);
    });

    test('falls back to the advertised default until a value is selected', () => {
        const target = offering();
        expect(getWmsDimensionSelection(target, elevation)).toBe('10');
        setWmsDimension(target, 'elevation', '0');
        expect(getWmsDimensionSelection(target, elevation)).toBe('0');
    });
});

describe('WMS dimensions in the context document', () => {
    test('imports advertised dimensions of every layer including inherited ones', () => {
        const capabilities = parseWms(dimensionsCapabilities);
        const resources = wmsToOWSResources('https://www.example.org/wms?SERVICE=WMS&', capabilities);
        const byName = (title: string) =>
            resources.find(resource => resource.properties.title === title)!.getWmsOffering()!.dimensions!;
        expect(byName('inheriting')).toEqual([
            { name: 'elevation', values: '0,10,20', units: 'CRS:84', unitSymbol: 'm', default: '10' },
            { name: 'DIM_sensor', values: '0/100/10', units: 'C', default: '0' },
        ]);
        expect(byName('overriding').find(dimension => dimension.name === 'DIM_sensor'))
            .toEqual({ name: 'DIM_sensor', values: '5,15' });
    });

    test('round trips selections through the document and keeps them out of shared batches', () => {
        const context = new OWSContext(undefined, [
            new OWSResource({ title: 'group', updated: '2026-10-23T08:00:00Z', folder: '/0' }),
            new OWSResource({ title: 'first', updated: '2026-10-23T08:00:00Z', folder: '/0/0', offerings: [offering()] }),
            new OWSResource({ title: 'second', updated: '2026-10-23T08:00:00Z', folder: '/0/1', offerings: [{
                ...offering(),
                operations: offering().operations!.map(operation => ({
                    ...operation,
                    href: operation.href.replace('LAYERS=a', 'LAYERS=b'),
                })),
            }] }),
        ]);
        setWmsDimension(context.features[1].getWmsOffering()!, 'elevation', '20');
        setWmsDimension(context.features[2].getWmsOffering()!, 'elevation', '20');

        const validated = validateOwsContext(JSON.parse(JSON.stringify(context)));
        expect(validated.issues.filter(issue => issue.severity === 'error')).toEqual([]);
        const reloaded = OWSContext.fromPlainObject(validated.context!);
        expect(reloaded.features[1].getWmsOffering()!.dimensions).toEqual([elevation, sensor]);
        const maps = reloaded.getOptimizedUrlsByCode('GetMap', () => true);
        expect(maps).toHaveLength(1);
        expect(maps[0].url.searchParams.get('LAYERS')).toBe('a,b');
        expect(maps[0].url.searchParams.get('ELEVATION')).toBe('20');

        // a sibling that asks for another slice of the cube must not share the request
        setWmsDimension(reloaded.features[2].getWmsOffering()!, 'elevation', '0');
        const split = reloaded.getOptimizedUrlsByCode('GetMap', () => true);
        expect(split).toHaveLength(2);
        expect(split.map(batch => batch.url.searchParams.get('ELEVATION')).sort()).toEqual(['0', '20']);
    });

    test('rejects malformed dimension members during import', () => {
        const broken = new OWSContext(undefined, [
            new OWSResource({ title: 'broken', updated: '2026-10-23T08:00:00Z', folder: '/0', offerings: [{
                code: WMS_OFFERING_CODE,
                dimensions: [{ name: 'elevation' } as unknown as OfferingDimension],
                operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a', active: true }],
            }] }),
        ]);
        const validated = validateOwsContext(JSON.parse(JSON.stringify(broken)));
        expect(validated.issues.some(issue =>
            issue.severity === 'error' && issue.path.endsWith('dimensions[0].values'))).toBe(true);
    });
});
