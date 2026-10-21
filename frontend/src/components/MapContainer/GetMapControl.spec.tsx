import type { PropsWithChildren } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render as testingRender, screen, waitFor } from '@testing-library/react';
import { latLng, latLngBounds, point } from 'leaflet';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import { OptimizedUrlsMap } from '../../ows-lib/OwsContext/core';
import WebMapServiceControl from './GetMapControl';

const state = vi.hoisted(() => ({
    context: {} as import('../../ows-lib/OwsContext/types').OWSContext,
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
vi.mock('../Resource/Generic/ServiceShow/LivePreview/LivePreview', () => ({ FeatureInfoResult: ({ text }: { text: string }) => <pre>{text}</pre> }));
vi.mock('react-admin', () => ({
    useTranslate: () => (key: string) => key,
    Link: ({ to, children }: PropsWithChildren<{ to: string }>) => <a href={to}>{children}</a>,
}));
vi.mock('../../react-ows-lib/ContextProvider/OwsContextBase', () => ({
    useOwsContextBase: () => ({ owsContext: state.context }),
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
const render = (ui: import('react').ReactNode) => testingRender(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
afterEach(() => vi.unstubAllGlobals());
const batch = (params: string): OptimizedUrlsMap => ({
    url: new URL(`https://example.org/wms?VERSION=1.3.0&${params}`),
    features: [],
    operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms' }],
});
beforeEach(() => {
    state.context = {} as typeof state.context;
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


test('fetches protected identify results with the assigned headers and blocks missing credentials', async () => {
    state.context.authenticationHeaders = [{ id: 'info', type: 'header', origin: 'https://example.org', name: 'Authorization', value: 'Basic secret' }];
    state.info = [batch('QUERY_LAYERS=a')];
    state.info[0].operations[0]['x-authentication-id'] = 'info';
    const fetch = vi.fn().mockResolvedValue({ ok: true, text: async () => '<script>unsafe</script>', headers: new Headers({ 'content-type': 'text/html' }) });
    vi.stubGlobal('fetch', fetch);
    const { rerender } = render(<WebMapServiceControl />);
    act(() => state.onContextMenu?.({ latlng: latLng(5, 5), containerPoint: point(20, 30) }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const options = fetch.mock.calls[0][1];
    expect(options.headers.get('Authorization')).toBe('Basic secret');
    expect(options).toMatchObject({ redirect: 'error', credentials: 'omit', signal: expect.any(AbortSignal) });
    expect(await screen.findByText('<script>unsafe</script>')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    state.context = { ...state.context, authenticationHeaders: [] };
    rerender(<QueryClientProvider client={new QueryClient()}><WebMapServiceControl /></QueryClientProvider>);
    expect(screen.getByRole('alert')).toHaveTextContent('viewerAuth.missing');
    expect(fetch).toHaveBeenCalledTimes(1);
});
