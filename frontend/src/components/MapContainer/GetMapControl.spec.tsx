import type { PropsWithChildren } from 'react';

import { act, render, screen } from '@testing-library/react';
import { latLng, latLngBounds, point } from 'leaflet';
import { beforeEach, expect, test, vi } from 'vitest';

import { OptimizedUrlsMap } from '../../ows-lib/OwsContext/core';
import WebMapServiceControl from './GetMapControl';

const state = vi.hoisted(() => ({
    maps: [] as OptimizedUrlsMap[],
    info: [] as OptimizedUrlsMap[],
    onContextMenu: undefined as undefined | ((event: unknown) => void),
}));
const map = {
    getBounds: () => latLngBounds([0, 0], [10, 10]),
    getSize: () => point(256, 256),
    on: vi.fn(),
    off: vi.fn(),
};
vi.mock('react-leaflet', () => ({
    useMap: () => map,
    useMapEvent: (_name: string, handler: typeof state.onContextMenu) => { state.onContextMenu = handler; },
    Marker: ({ children }: PropsWithChildren) => <>{children}</>,
    Popup: ({ children }: PropsWithChildren) => <>{children}</>,
    Tooltip: () => null,
}));
vi.mock('react-admin', () => ({
    Link: ({ to, children }: PropsWithChildren<{ to: string }>) => <a href={to}>{children}</a>,
}));
vi.mock('../../react-ows-lib/ContextProvider/OwsContextBase', () => ({
    useOwsContextBase: () => ({ owsContext: {} }),
}));
vi.mock('../MapViewer/MapViewerBase', () => ({
    useMapViewerBase: () => ({
        selectedCrs: { stringRepresentation: 'EPSG:4326', isXyOrder: true },
        atomicGetMapUrls: state.maps,
        atomicGetFeatureInfoUrls: state.info,
    }),
}));
vi.mock('./AuthImageOverlay', () => ({
    AuthImageOverlay: ({ optimiuedUrl }: { optimiuedUrl: OptimizedUrlsMap }) => (
        <span data-testid="image-url">{optimiuedUrl.url.href}</span>
    ),
}));
const batch = (params: string): OptimizedUrlsMap => ({
    url: new URL(`https://example.org/wms?VERSION=1.3.0&${params}`),
    features: [],
    operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms' }],
});
beforeEach(() => {
    state.maps = [];
    state.info = [];
});

test('the final map URL preserves configured positional styles and vendor parameters', () => {
    state.maps = [batch('LAYERS=a,b&STYLES=outline,fill&token=map')];
    render(<WebMapServiceControl />);
    const url = new URL(screen.getByTestId('image-url').textContent!);
    expect(url.searchParams.get('LAYERS')).toBe('a,b');
    expect(url.searchParams.get('STYLES')).toBe('outline,fill');
    expect(url.searchParams.get('token')).toBe('map');
    expect(url.searchParams.get('WIDTH')).toBe('256');
});

test('the final feature info URL preserves map layers, query subset and styles', () => {
    state.info = [batch('LAYERS=backdrop,a,b&QUERY_LAYERS=a,b&STYLES=,outline,fill&token=info')];
    render(<WebMapServiceControl />);
    act(() => state.onContextMenu?.({ latlng: latLng(5, 5), containerPoint: point(20, 30) }));
    const url = new URL(screen.getByRole('link').getAttribute('href')!);
    expect(url.searchParams.get('LAYERS')).toBe('backdrop,a,b');
    expect(url.searchParams.get('QUERY_LAYERS')).toBe('a,b');
    expect(url.searchParams.get('STYLES')).toBe(',outline,fill');
    expect(url.searchParams.get('token')).toBe('info');
    expect(url.searchParams.get('I')).toBe('20');
    expect(url.searchParams.get('J')).toBe('30');
});

test('keeps the defaults for requests without styles or feature info map layers', () => {
    state.maps = [batch('LAYERS=a')];
    state.info = [batch('QUERY_LAYERS=a')];
    render(<WebMapServiceControl />);
    expect(new URL(screen.getByTestId('image-url').textContent!).searchParams.get('STYLES')).toBe('');
    act(() => state.onContextMenu?.({ latlng: latLng(5, 5), containerPoint: point(20, 30) }));
    const params = new URL(screen.getByRole('link').getAttribute('href')!).searchParams;
    expect(params.get('LAYERS')).toBe('a');
    expect(params.get('STYLES')).toBe('');
});
