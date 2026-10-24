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

const openStyleControls = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'viewerControls.edit' }));
  await screen.findByRole('region', { name: 'viewerControls.edit' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
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
    await openStyleControls();
    expect(screen.getByRole('combobox')).toHaveValue('outline');
    expect(document.querySelector('[role=tree] [role=region]')).toBeNull();
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

    fireEvent.click(screen.getByRole('button', { name: 'ra.action.close' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'viewerControls.edit' })).not.toBeInTheDocument());
    fireEvent.click(screen.getByText('Reload context'));
    await openStyleControls();
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
    await openStyleControls();
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

  it('opens layer settings through the existing right-click context menu', async () => {
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
    expect(await screen.findByRole('region', { name: 'viewerControls.edit' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox')).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'ra.action.close' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'viewerControls.edit' })).not.toBeInTheDocument());
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
    const { container } = render(<LayerTree />, {wrapper: MapViewerBaseWrapper})

    // the folders of an arriving tree are expanded by default; a collapsed folder keeps
    // its subtree in the dom hidden, so the expansion itself is asserted. The row element
    // also contains the rows below it, so the arrow is picked inside the row's own content
    const rootRow = container.querySelector('[data-owscontext-folder="/0"]') as HTMLElement
    expect(rootRow).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(rootRow.querySelector(':scope > div svg[data-testid="KeyboardArrowDownIcon"]') as Element)
    expect(rootRow).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(rootRow.querySelector(':scope > div svg[data-testid="KeyboardArrowRightIcon"]') as Element)
    expect(rootRow).toHaveAttribute('aria-expanded', 'true');
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

    // the group which no resource of the context describes is rendered by its own name, and the
    // root of an imported tree opens so its leaf sits in view right away
    expect(screen.getByText('Umwelt')).toBeInTheDocument();
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

  it('marks an active layer out of scale without touching its activation', () => {
    const feature = new OWSResource({
      title: 'Scaled Layer', updated: '', folder: '/0', active: true,
      maxscaledenominator: 1000,
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        operations: [
          { code: 'GetMap', method: 'GET', href: 'https://example.com/wms', active: true },
        ],
      }],
    });

    viewerState.scaleDenominator = 5000;
    render(
      <AdminContext><OwsContextBase initialFeatures={[feature]}>
        <LayerTree />
        <ContextProbe />
      </OwsContextBase></AdminContext>
    );

    // the viewer knows the view is out of the advertised limits and says so in the tree
    expect(screen.getByLabelText('viewerScale.notRenderedShort')).toBeInTheDocument();
    // the indicator only explains the suppressed rendering: the user's activation stays untouched
    expect(screen.getByTestId('get-map-state')).toHaveTextContent('true');
    viewerState.scaleDenominator = undefined;
  });
});

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

  it("opens the folders of a tree that arrives after the mount", () => {
    const root = new OWSResource({
      title: 'wfs service', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc-geojson/1.0/req/wfs',
        operations: [{ code: 'GetCapabilities', method: 'GET', href: 'https://example.org/wfs' }],
        version: '2.0.0',
      }],
    });
    const leaf = new OWSResource({
      title: 'buildings', updated: '', folder: '/0/1', active: false,
      offerings: [{
        code: 'http://www.opengis.net/spec/owc-geojson/1.0/req/wfs',
        operations: [{ code: 'GetFeature', method: 'GET', href: 'https://example.org/wfs?TYPENAME=buildings' }],
        version: '2.0.0',
        qualifiedName: 'buildings',
        outputFormats: ['application/json'],
        defaultCrs: 'EPSG:4326',
        otherCrs: [],
      }],
    });

    const Adder = () => {
      const { setOwsContext } = useOwsContextBase();
      return <button onClick={() => setOwsContext(new OWSContext(undefined, [new OWSResource(leaf.properties, leaf.id, leaf.bbox, leaf.geometry), new OWSResource(root.properties, root.id, root.bbox, root.geometry)]))}>add tree</button>;
    };

    render(<AdminContext><OwsContextBase><Adder /><LayerTree /></OwsContextBase></AdminContext>);

    // an imported tree must not hide its types behind a closed root
    expect(screen.queryByText('buildings')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('add tree'));

    expect(screen.getByText('buildings')).toBeInTheDocument();
    const leafCheckbox = screen.getAllByRole('checkbox')
      .find(checkbox => checkbox.closest('[role=treeitem]')?.textContent?.includes('buildings'));
    fireEvent.click(leafCheckbox as HTMLElement);

    // the folder paths are normalized onto complete numbered trees, so the type sits at '/0/0'
    const leafActive = () => document.querySelector('[role=treeitem][data-owscontext-folder="/0/0"] input[type=checkbox]') as HTMLInputElement | null;
    expect(leafActive()?.checked).toBe(true);
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

  it('activates a WFS type through the resource itself and keeps WMS identify out of its row', () => {
    const root = new OWSResource({
      title: 'wfs service', updated: '', folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc-geojson/1.0/req/wfs',
        operations: [{ code: 'GetCapabilities', method: 'GET', href: 'https://example.org/wfs' }],
        version: '2.0.0',
      }],
    });
    const leaf = new OWSResource({
      title: 'buildings', updated: '', folder: '/0/0', active: false,
      offerings: [{
        code: 'http://www.opengis.net/spec/owc-geojson/1.0/req/wfs',
        operations: [{ code: 'GetFeature', method: 'GET', href: 'https://example.org/wfs?TYPENAME=buildings' }],
        version: '2.0.0',
        qualifiedName: 'buildings',
        outputFormats: ['application/json'],
        defaultCrs: 'EPSG:4326',
        otherCrs: [],
      }],
    });

    const WfsProbe = () => {
      const { owsContext } = useOwsContextBase();
      return <>
        <span data-testid="leaf-active">{String(owsContext.findResourceByFolder('/0/0')?.properties.active ?? false)}</span>
        <span data-testid="root-active">{String(owsContext.findResourceByFolder('/0')?.properties.active ?? false)}</span>
      </>;
    };

    render(<AdminContext><OwsContextBase initialFeatures={[root, leaf]}><LayerTree /><WfsProbe /></OwsContextBase></AdminContext>);

    // a WMS row carries two checkboxes, a WFS row only the visibility one
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
    expect(screen.getByTestId('leaf-active')).toHaveTextContent('false');

    fireEvent.click(checkboxes[1]);

    expect(screen.getByTestId('leaf-active')).toHaveTextContent('true');
    // the group of a fully active subtree answers active as well
    expect(screen.getByTestId('root-active')).toHaveTextContent('true');

    // react-admin hands the same input element over to the re-rendered row, so its checked
    // property is stale after the activation - the tree's second row is asked for the leaf again
    fireEvent.click(screen.getAllByRole('checkbox')[1]);

    expect(screen.getByTestId('leaf-active')).toHaveTextContent('false');
  });
});

const viewerState: {
  mapLoading: { failedFeatures: unknown[], errors: unknown[] };
  scaleDenominator?: number;
} = { mapLoading: { failedFeatures: [], errors: [] }, scaleDenominator: undefined };

vi.mock("../MapViewer/MapViewerBase", () => ({ useMapViewerBase: () => viewerState }));
