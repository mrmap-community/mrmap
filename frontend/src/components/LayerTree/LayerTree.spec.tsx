import { ReactNode } from 'react';
import { AdminContext } from "react-admin";

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core';
import { karteRpFeatures as testdata } from '../../ows-lib/OwsContext/tests/data';
import { OwsContextBase, useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase';
import LayerTree from './LayerTree';


const getKarteRpFeatures = () => {
  return testdata.map(resource => new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry));
}

const MapViewerBaseWrapper = ({ children }: { children: ReactNode }) => {
  return (
    <AdminContext><OwsContextBase initialFeatures={getKarteRpFeatures()}>
      {children}
    </OwsContextBase></AdminContext>
  )
}


const ContextProbe = () => {
  const { owsContext, setOwsContext } = useOwsContextBase();
  const target = owsContext.findResourceByFolder('/0');
  const getMapOperation = target?.getWmsOperationByCode('GetMap');
  const getFeatureInfoOperation = target?.getWmsOperationByCode('GetFeatureInfo');

  return (
    <div>
      <span data-testid="get-map-state">{String(getMapOperation?.active ?? false)}</span>
      <span data-testid="get-feature-info-state">{String(getFeatureInfoOperation?.active ?? false)}</span>
      <span data-testid="map-href">{getMapOperation?.href}</span>
      <span data-testid="info-href">{getFeatureInfoOperation?.href}</span>
      <button onClick={() => setOwsContext(OWSContext.fromPlainObject(JSON.parse(JSON.stringify(owsContext))))}>Reload context</button>
    </div>
  );
};

const openStyleDialog = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'viewerStyles.options' }));
  fireEvent.click(await screen.findByRole('menuitem', { name: 'viewerStyles.title' }));
  await screen.findByRole('dialog');
};

describe('LayerTree', () => {
  it('selects advertised styles, reloads them and displays legend loading, success and failure states', async () => {
    const feature = new OWSResource({
      title: 'Styled layer', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        styles: [
          { name: 'outline', title: 'Outline', legendURL: 'https://example.org/outline.png' },
          { name: 'fill', title: 'Fill', legendURL: 'https://example.org/fill.png' },
          { name: 'no-legend', title: 'No legend' },
        ],
        operations: [
          { code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a&STYLES=outline', active: true },
          { code: 'GetFeatureInfo', method: 'GET', href: 'https://example.org/wms?LAYERS=a&QUERY_LAYERS=a&STYLES=outline', active: false },
        ],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[feature]}><LayerTree /><ContextProbe /></OwsContextBase></AdminContext>);

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { hidden: true })).not.toBeInTheDocument();
    expect(screen.queryByText('viewerStyles.unavailable')).not.toBeInTheDocument();
    await openStyleDialog();
    expect(screen.getByRole('combobox')).toHaveValue('outline');
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'viewerStyles.loading');
    const first = screen.getByRole('img', { hidden: true });
    expect(first).toHaveAttribute('src', 'https://example.org/outline.png');
    fireEvent.load(first);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'fill' } });
    expect(new URL(screen.getByTestId('map-href').textContent!).searchParams.get('STYLES')).toBe('fill');
    expect(new URL(screen.getByTestId('info-href').textContent!).searchParams.get('STYLES')).toBe('fill');
    expect(screen.getByTestId('get-map-state')).toHaveTextContent('true');
    expect(screen.getByTestId('get-feature-info-state')).toHaveTextContent('false');
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'viewerStyles.loading');
    fireEvent.error(screen.getByRole('img', { hidden: true }));
    expect(screen.getByRole('status')).toHaveTextContent('viewerStyles.unavailable');

    fireEvent.click(screen.getByRole('button', { name: 'viewerStyles.done' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    fireEvent.click(screen.getByText('Reload context'));
    await openStyleDialog();
    expect(screen.getByRole('combobox')).toHaveValue('fill');
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'no-legend' } });
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('viewerStyles.unavailable');
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } });
    expect(new URL(screen.getByTestId('map-href').textContent!).searchParams.get('STYLES')).toBe('');
  });

  it('keeps unadvertised imported styles until the user chooses a replacement', async () => {
    const feature = new OWSResource({
      title: 'Imported layer', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        styles: [{ name: 'fill', title: 'Fill' }],
        operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a&STYLES=imported' }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[feature]}><LayerTree /><ContextProbe /></OwsContextBase></AdminContext>);
    await openStyleDialog();
    expect(screen.getByRole('combobox')).toHaveValue('imported');
    expect(screen.getByRole('option', { name: 'imported' })).toBeDisabled();
    expect(new URL(screen.getByTestId('map-href').textContent!).searchParams.get('STYLES')).toBe('imported');
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'fill' } });
    expect(new URL(screen.getByTestId('map-href').textContent!).searchParams.get('STYLES')).toBe('fill');
  });

  it.each([undefined, [], [{ name: '', title: 'Unnamed' }]])('disables the style menu action when no named styles are advertised: %j', async styles => {
    const feature = new OWSResource({
      title: 'No styles', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms', styles,
        operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a&STYLES=imported', active: true }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[feature]}><LayerTree /><ContextProbe /></OwsContextBase></AdminContext>);
    fireEvent.click(screen.getByRole('button', { name: 'viewerStyles.options' }));
    const action = await screen.findByRole('menuitem', { name: 'viewerStyles.title' });
    expect(action).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(action);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'viewerAuth.title' })).not.toHaveAttribute('aria-disabled', 'true');
    expect(new URL(screen.getByTestId('map-href').textContent!).searchParams.get('STYLES')).toBe('imported');
  });

  it('opens the style dialog through the existing right-click context menu', async () => {
    const feature = new OWSResource({
      title: 'Right-click layer', updated: '', folder: '/0',
      offerings: [{
        styles: [{ name: 'outline', title: 'Outline' }],
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a' }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[feature]}><LayerTree /></OwsContextBase></AdminContext>);
    fireEvent.contextMenu(screen.getByText('Right-click layer'), { clientX: 100, clientY: 100 });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'viewerStyles.title' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Right-click layer');
    expect(screen.getByRole('combobox')).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'ra.action.close' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows the selected style legend in the custom-style tooltip only on hover', async () => {
    const feature = new OWSResource({
      title: 'Styled layer', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        styles: [{ name: 'outline', title: 'Outline', legendURL: 'https://example.org/outline.png' }],
        operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a&STYLES=outline' }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[feature]}><LayerTree /></OwsContextBase></AdminContext>);
    expect(screen.queryByRole('img', { hidden: true })).not.toBeInTheDocument();
    fireEvent.mouseOver(screen.getByLabelText('viewerStyles.custom'));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('a · Outline');
    const image = screen.getByRole('img', { hidden: true });
    expect(image).toHaveAttribute('src', 'https://example.org/outline.png');
    fireEvent.load(image);
    expect(screen.getByRole('img')).toBeVisible();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('LayerTree renders with initial data', () => {
    render(<LayerTree />, {wrapper: MapViewerBaseWrapper})
    
    expect(screen.getByText('Karte RP')).toBeInTheDocument();
  });

  it('LayerTree renders with initial expanded values', () => {
    render(<LayerTree initialExpanded={['/0', '/0/1']}/>, {wrapper: MapViewerBaseWrapper})
    
    expect(screen.getByText('Karte RP')).toBeInTheDocument();
    expect(screen.getByText('Wald')).toBeInTheDocument();
    expect(screen.getByText('Wald 0')).toBeInTheDocument();
  });

  it('LayerTree is expandable', () => {
    render(<LayerTree />, {wrapper: MapViewerBaseWrapper})

    const expandIcon = screen.getByTestId('KeyboardArrowRightIcon')
    fireEvent.click(expandIcon)
    expect(screen.getByText('Wald')).toBeInTheDocument();
  });

  it('renders a grouping the context only names', () => {
    const customFeatures = [new OWSResource({
      title: 'Algen', updated: '',
      folder: '/Umwelt/Algen',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        operations: [
          { code: 'GetMap', method: 'GET', href: 'https://example.com/wms', active: true },
        ],
      }],
    })];

    render(
      <AdminContext><OwsContextBase initialFeatures={customFeatures}>
        <LayerTree />
      </OwsContextBase></AdminContext>
    );

    // the group which no resource of the context describes is rendered by its own name
    expect(screen.getByText('Umwelt')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('KeyboardArrowRightIcon'));
    expect(screen.getByText('Algen')).toBeInTheDocument();
  });

  it('toggles GetFeatureInfo via the second checkbox', () => {
    const customFeatures = [new OWSResource({
      title: 'Test Layer', updated: '',
      folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        operations: [
          { code: 'GetMap', method: 'GET', href: 'https://example.com/wms', active: false },
          { code: 'GetFeatureInfo', method: 'GET', href: 'https://example.com/wms', active: false },
        ],
      }],
    })];

    render(
      <AdminContext><OwsContextBase initialFeatures={customFeatures}>
        <LayerTree />
        <ContextProbe />
      </OwsContextBase></AdminContext>
    );

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);

    expect(screen.getByTestId('get-feature-info-state')).toHaveTextContent('true');
  });

  it('renders GetMap checkbox as indeterminate when descendants are mixed active', () => {
    const customFeatures = [
      new OWSResource({
        title: 'Parent Layer', updated: '',
        folder: '/0',
        offerings: [{
          code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
          operations: [
            { code: 'GetMap', method: 'GET', href: 'https://example.com/wms', active: true },
          ],
        }],
      }),
      new OWSResource({
        title: 'Child Layer', updated: '',
        folder: '/0/1',
        offerings: [{
          code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
          operations: [
            { code: 'GetMap', method: 'GET', href: 'https://example.com/wms', active: false },
          ],
        }],
      }),
    ];

    render(
      <AdminContext><OwsContextBase initialFeatures={customFeatures}>
        <LayerTree />
      </OwsContextBase></AdminContext>
    );

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[0]).toHaveAttribute('data-indeterminate', 'true');
  });
});
vi.mock("../MapViewer/MapViewerBase", () => ({ useMapViewerBase: () => ({ mapLoading: { failedFeatures: [], errors: [] } }) }));

describe('unsupported offerings', () => {
  it('marks a resource whose offering the viewer cannot render and leaves a renderable one alone', () => {
    const wmts = new OWSResource({
      title: 'wmts layer', updated: '', folder: '/0', active: true,
      offerings: [{
        code: 'http://www.opengis.net/spec/owc-geojson/1.0/req/wmts',
        operations: [{ code: 'GetTile', method: 'GET', href: 'https://example.org/wmts' }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[wmts]}><LayerTree /></OwsContextBase></AdminContext>);

    expect(screen.getByTestId('WarningAmberIcon')).toBeInTheDocument();
  });

  it('marks a resource whose GetMap is offered as POST only', () => {
    const postOnly = new OWSResource({
      title: 'post layer', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc-geojson/1.0/req/wms',
        operations: [{ code: 'GetMap', method: 'POST', href: 'https://example.org/wms?A', active: true }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[postOnly]}><LayerTree /></OwsContextBase></AdminContext>);

    expect(screen.getByTestId('WarningAmberIcon')).toBeInTheDocument();
  });

  it('leaves a resource the viewer can render unmarked', () => {
    const renderable = new OWSResource({
      title: 'wms layer', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc-geojson/1.0/req/wms',
        operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms?A', active: true }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[renderable]}><LayerTree /></OwsContextBase></AdminContext>);

    expect(screen.queryByTestId('WarningAmberIcon')).not.toBeInTheDocument();
  });
});
