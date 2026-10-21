import { describe, expect, test } from 'vitest';

import { OWSContext, OWSResource } from './core';
import { Operation } from './types';

const operation = (code: string, layers: string, params = '', auth?: string): Operation => ({
    code,
    method: 'GET',
    href: `https://example.org/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=${code}&LAYERS=${layers}${code === 'GetFeatureInfo' ? `&QUERY_LAYERS=${layers}` : ''}${params}`,
    active: true,
    ...(auth !== undefined && { 'x-authentication-id': auth }),
});

const contextFor = (operations: Operation[]) => new OWSContext(undefined, [
    new OWSResource({ title: 'group', updated: '', folder: '/0' }),
    ...operations.map((item, index) => new OWSResource({
        title: `layer ${index}`,
        updated: '',
        folder: `/0/${index}`,
        offerings: [{ code: 'http://www.opengis.net/spec/owc/1.0/req/wms', operations: [item] }],
    }, index)),
]);

const batchesFor = (code: string, operations: Operation[]) => contextFor(operations).getOptimizedUrlsByCode(
    code, feature => feature.getWmsOperationByCode(code)?.active === true,
);

describe.each(['GetMap', 'GetFeatureInfo'])('%s request batching', code => {
    test('batches compatible parameters and keeps layer/style positions, including defaults', () => {
        const operations = [
            operation(code, 'a,b', '&STYLES=outline,&TIME=2026&token=shared', 'auth'),
            operation(code, 'c', '&TIME=2026&token=shared', 'auth'),
            operation(code, 'd', '&STYLES=fill&token=shared&TIME=2026', 'auth'),
        ];
        const before = operations.map(item => item.href);
        const batches = batchesFor(code, operations);
        expect(batches).toHaveLength(1);
        expect(batches[0].url.searchParams.get('LAYERS')).toBe('a,b,c,d');
        expect(batches[0].url.searchParams.get('STYLES')).toBe('outline,,,fill');
        expect(batches[0].url.searchParams.get('TIME')).toBe('2026');
        expect(batches[0].url.searchParams.get('token')).toBe('shared');
        if (code === 'GetFeatureInfo') expect(batches[0].url.searchParams.get('QUERY_LAYERS')).toBe('a,b,c,d');
        expect(batches[0].features.map(feature => feature.id)).toEqual([0, 1, 2]);
        expect(batches[0].operations).toEqual(operations);
        expect(operations.map(item => item.href)).toEqual(before);
    });

    test.each(['CQL_FILTER', 'FILTER', 'TIME', 'ELEVATION', 'SLD', 'SLD_BODY', 'route', 'token', 'FORMAT', 'CRS', 'INFO_FORMAT'])(
        'keeps different %s values separate', key => {
            const operations = [operation(code, 'a', `&${key}=first`), operation(code, 'b', `&${key}=second`)];
            const batches = batchesFor(code, operations);
            expect(batches).toHaveLength(2);
            expect(batches.map(batch => batch.url.href)).toEqual(operations.map(item => item.href));
        },
    );

    test.each(['CQL_FILTER', 'FILTER', 'SLD', 'SLD_BODY'])(
        'does not reinterpret layer-dependent %s values even when equal', key => {
            expect(batchesFor(code, [operation(code, 'a', `&${key}=same`), operation(code, 'b', `&${key}=same`)])).toHaveLength(2);
        },
    );

    test('keeps absent and present vendor parameters separate', () => {
        expect(batchesFor(code, [operation(code, 'a'), operation(code, 'b', '&token=')])).toHaveLength(2);
    });

    test.each([[undefined, 'auth'], ['auth', undefined], ['first', 'second']])(
        'keeps authentication assignments %s and %s separate', (first, second) => {
            expect(batchesFor(code, [operation(code, 'a', '', first), operation(code, 'b', '', second)])).toHaveLength(2);
        },
    );

    test('keeps URL credentials separate', () => {
        const second = operation(code, 'b');
        second.href = second.href.replace('example.org', 'user:secret@example.org');
        expect(batchesFor(code, [operation(code, 'a'), second])).toHaveLength(2);
    });

    test('preserves drawing order across incompatible batches', () => {
        const batches = batchesFor(code, [operation(code, 'a', '&TIME=first'), operation(code, 'b', '&TIME=second'), operation(code, 'c', '&TIME=first')]);
        expect(batches.map(batch => batch.url.searchParams.get('LAYERS'))).toEqual(['a', 'b', 'c']);
    });

    test('handles mixed-case WMS keys without changing vendor key casing', () => {
        const second = operation(code, 'b', '&STYLES=fill');
        second.href = second.href.replace('LAYERS=b', 'LaYeRs=b').replace('STYLES', 'Styles');
        const batches = batchesFor(code, [operation(code, 'a'), second]);
        expect(batches).toHaveLength(1);
        expect(batches[0].url.searchParams.get('LAYERS')).toBe('a,b');
        expect(batches[0].url.searchParams.get('STYLES')).toBe(',fill');
        expect(batchesFor(code, [operation(code, 'a', '&token=one'), operation(code, 'b', '&Token=one')])).toHaveLength(2);
    });

    test.each(['&STYLES=one,two', '&LAYERS=other', '&layers=other', '&token=one&token=two'])(
        'leaves ambiguous parameters untouched: %s', params => {
            const operations = [operation(code, 'a', params), operation(code, 'b', params)];
            expect(batchesFor(code, operations).map(batch => batch.url.href)).toEqual(operations.map(item => item.href));
        },
    );

    test('allows a caller to restrict batching but not bypass compatibility', () => {
        const context = contextFor([operation(code, 'a', '&TIME=one'), operation(code, 'b', '&TIME=two')]);
        const active = (feature: OWSResource) => feature.getWmsOperationByCode(code)?.active === true;
        expect(context.getOptimizedUrlsByCode(code, active, () => true)).toHaveLength(2);
        expect(contextFor([operation(code, 'a'), operation(code, 'b')]).getOptimizedUrlsByCode(code, active, () => false)).toHaveLength(2);
    });
});

test('GetMap and GetFeatureInfo activation remain independent', () => {
    const context = contextFor([operation('GetMap', 'map-only'), operation('GetFeatureInfo', 'info-only')]);
    for (const code of ['GetMap', 'GetFeatureInfo']) {
        const batches = context.getOptimizedUrlsByCode(code, feature => feature.getWmsOperationByCode(code)?.active === true);
        expect(batches).toHaveLength(1);
        expect(batches[0].url.searchParams.get('LAYERS')).toBe(code === 'GetMap' ? 'map-only' : 'info-only');
    }
});
