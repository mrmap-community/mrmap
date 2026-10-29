import type { PropsWithChildren } from 'react';
import { AdminContext } from 'react-admin';

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OWSResource } from '../../ows-lib/OwsContext/core';
import { OwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase';
import { MapViewerCore } from './MapViewer';

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: PropsWithChildren) => <div data-testid="map">{children}</div>,
  ScaleControl: () => null,
}));
vi.mock('./MapViewerBase', () => ({
  MapViewerBase: ({ children }: PropsWithChildren) => children,
  useMapViewerBase: () => ({
    setMap: vi.fn(),
    mapLoading: { errors: [], failedFeatures: [] },
    opacityOf: () => 1,
    setLayerOpacity: vi.fn(),
  }),
}));
vi.mock('../MapContainer/GetMapControl', () => ({ default: () => null }));
vi.mock('../MapContainer/GetFeatureControl', () => ({ default: () => null }));
vi.mock('./OwsContextGuiActions/OwsContextGuiActions', () => ({ OwsContextActionButtons: () => null }));
vi.mock('./StatusBar', () => ({ default: () => null }));
vi.mock('./MapSettings', () => ({ default: () => <div>Map settings</div> }));
vi.mock('../../jsonapi/components/ListGuesser', () => ({ default: () => null }));

const layer = (name: string, folder: string) => new OWSResource({
  title: name, folder, updated: '', offerings: [{
    code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
    styles: [{ name: 'outline', title: 'Outline' }],
    dimensions: [{ name: 'time', units: 'ISO8601', values: '2026-01-01/2026-01-03/P1D', default: '2026-01-02' }],
    operations: [{ code: 'GetMap', method: 'GET', href: `https://example.test/wms?LAYERS=${name}`, active: true }],
  }],
});

describe('viewer layer settings drawer', () => {
  it('opens the settings tab from a compact tree row and switches layers in the same panel', async () => {
    render(<AdminContext><OwsContextBase initialFeatures={[layer('Radar A', '/0'), layer('Radar B', '/1')]}><MapViewerCore /></OwsContextBase></AdminContext>);
    // Open the existing right-hand drawer; its tree stays mounted when settings open.
    fireEvent.click(screen.getByTestId('ChevronLeftIcon').closest('button')!);
    const tree = screen.getAllByRole('tree')[0].parentElement!;
    fireEvent.click(within(tree).getByText('Radar A'));
    await waitFor(() => expect(screen.getByRole('tab', { name: 'viewerControls.title' })).toHaveAttribute('aria-selected', 'true'));
    expect(screen.getByRole('button', { name: 'drawer.closeBottom' })).toBeInTheDocument();
    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveTextContent('Radar A');
    expect(within(panel).getByRole('slider', { name: /^viewerDimensions.dimension/ })).toHaveValue('1');
    // the blending of the layer is edited in the same panel, at full opacity by default (#750)
    expect(within(panel).getByRole('slider', { name: 'viewerControls.opacity' })).toHaveValue('100');
    expect(within(tree).queryByRole('slider')).toBeNull();
    expect(within(tree).queryByRole('combobox')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.change(within(panel).getByRole('combobox', { name: 'viewerStyles.style' }), { target: { value: 'outline' } });
    expect(within(panel).getByRole('combobox', { name: 'viewerStyles.style' })).toHaveValue('outline');
    fireEvent.click(within(tree).getByText('Radar B'));
    expect(screen.getByRole('button', { name: 'drawer.closeBottom' })).toBeInTheDocument();
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(panel).toHaveTextContent('Radar B');
    expect(within(panel).getByRole('combobox', { name: 'viewerStyles.style' })).toHaveValue('');
    expect(within(tree).getByText('Radar A')).toBeVisible();
    expect(within(tree).getByText('Radar B')).toBeVisible();
    fireEvent.click(within(tree).getByText('Radar A'));
    expect(screen.getByRole('button', { name: 'drawer.closeBottom' })).toBeInTheDocument();
    expect(within(panel).getByRole('combobox', { name: 'viewerStyles.style' })).toHaveValue('outline');
    fireEvent.click(screen.getByRole('tab', { name: 'Map Settings' }));
    fireEvent.click(within(tree).getByText('Radar A'));
    expect(screen.getByRole('button', { name: 'drawer.closeBottom' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'viewerControls.title' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Radar A');
  });
});
