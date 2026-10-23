import { describe, expect, test } from 'vitest';

import { OWSContext, OWSResource } from './core';
import { Offering } from './types';
import { getWmsOperationStyles, setWmsLayerStyle } from './utils';
import { validateOwsContext, WMS_OFFERING_CODE } from './validation';

const offering = (): Offering => ({
    code: WMS_OFFERING_CODE,
    styles: [{ name: 'outline', title: 'Outline' }, { name: 'fill', title: 'Fill', legendURL: 'https://example.org/legend.png' }],
    operations: [
        { code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a,b&Styles=outline,&token=map', active: true },
        { code: 'GetFeatureInfo', method: 'GET', href: 'https://example.org/wms?LaYeRs=backdrop,b,a&QUERY_LAYERS=a&STYLES=,old,outline&token=info', active: false },
    ],
});

describe('WMS style selection', () => {
    test('changes matching layer positions in both operations without changing activation or query subsets', () => {
        const target = offering();
        setWmsLayerStyle(target, 'b', 'fill');
        const [map, info] = target.operations!;
        expect(getWmsOperationStyles(map)).toEqual([{ layer: 'a', style: 'outline' }, { layer: 'b', style: 'fill' }]);
        expect(getWmsOperationStyles(info)).toEqual([{ layer: 'backdrop', style: '' }, { layer: 'b', style: 'fill' }, { layer: 'a', style: 'outline' }]);
        expect(map.active).toBe(true);
        expect(info.active).toBe(false);
        expect(new URL(map.href).searchParams.get('Styles')).toBe('outline,fill');
        expect(new URL(info.href).searchParams.get('QUERY_LAYERS')).toBe('a');
        expect(new URL(info.href).searchParams.get('token')).toBe('info');
        setWmsLayerStyle(target, 'a', '');
        expect(getWmsOperationStyles(map)[0].style).toBe('');
    });

    test('preserves unknown imported styles and rejects unsupported choices and ambiguous URLs', () => {
        const target = offering();
        const before = JSON.stringify(target);
        setWmsLayerStyle(target, 'b', 'unsupported');
        expect(JSON.stringify(target)).toBe(before);
        target.operations![0].href += '&STYLES=duplicate';
        const ambiguous = target.operations![0].href;
        setWmsLayerStyle(target, 'b', 'fill');
        expect(target.operations![0].href).toBe(ambiguous);
        expect(getWmsOperationStyles(target.operations![0])).toEqual([]);
    });

    test('fills default style positions when the imported URL omits STYLES', () => {
        const target = offering();
        target.operations![0].href = 'https://example.org/wms?LAYERS=a,b';
        setWmsLayerStyle(target, 'b', 'fill');
        expect(new URL(target.operations![0].href).searchParams.get('STYLES')).toBe(',fill');
    });

    test('updates legacy identify URLs that only specify QUERY_LAYERS', () => {
        const target = offering();
        target.operations![1].href = 'https://example.org/wms?QUERY_LAYERS=b,a&STYLES=,outline';
        setWmsLayerStyle(target, 'b', 'fill');
        expect(new URL(target.operations![1].href).searchParams.get('STYLES')).toBe('fill,outline');
    });

    test('exports and reloads selected styles and legends before building combined request URLs', () => {
        const context = new OWSContext(undefined, [
            new OWSResource({ title: 'group', updated: '2026-10-23T08:00:00Z', folder: '/0' }),
            new OWSResource({ title: 'first', updated: '2026-10-23T08:00:00Z', folder: '/0/0', offerings: [offering()] }),
            new OWSResource({ title: 'second', updated: '2026-10-23T08:00:00Z', folder: '/0/1', offerings: [{
                ...offering(), operations: offering().operations!.map(operation => ({
                    ...operation,
                    href: `https://example.org/wms?LAYERS=c&STYLES=${operation.code === 'GetMap' ? '' : 'fill'}&token=${operation.code === 'GetMap' ? 'map' : 'info'}${operation.code === 'GetFeatureInfo' ? '&QUERY_LAYERS=c' : ''}`,
                })),
            }] }),
        ]);
        setWmsLayerStyle(context.features[1].getWmsOffering()!, 'b', 'fill');
        const validated = validateOwsContext(JSON.parse(JSON.stringify(context)));
        expect(validated.issues.filter(issue => issue.severity === 'error')).toEqual([]);
        const reloaded = OWSContext.fromPlainObject(validated.context!);
        expect(reloaded.features[1].getWmsOffering()!.styles).toEqual(offering().styles);
        const maps = reloaded.getOptimizedUrlsByCode('GetMap', () => true);
        expect(maps).toHaveLength(1);
        expect(maps[0].url.searchParams.get('LAYERS')).toBe('a,b,c');
        expect(maps[0].url.searchParams.get('Styles')).toBe('outline,fill,');
        const info = reloaded.getOptimizedUrlsByCode('GetFeatureInfo', () => true);
        expect(info).toHaveLength(1);
        expect(info[0].url.searchParams.get('LaYeRs')).toBe('backdrop,b,a,c');
        expect(info[0].url.searchParams.get('STYLES')).toBe(',fill,outline,fill');
        expect(info[0].url.searchParams.get('QUERY_LAYERS')).toBe('a,c');
        expect(reloaded.getOptimizedUrlsByCode('GetFeatureInfo', feature => feature.getWmsOperationByCode('GetFeatureInfo')?.active === true)).toEqual([]);
    });
});
