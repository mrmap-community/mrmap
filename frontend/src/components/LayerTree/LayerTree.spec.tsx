import { ReactNode } from 'react';
import { AdminContext } from "react-admin";

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
      <span data-testid="wfs-requests">{owsContext.getWfsFeatureRequests().map(({ feature }) => feature.properties.title).join(',')}</span>
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
  it('toggles WFS offerings individually and as a group using resource activation', () => {
    const offerings = [{
      code: 'http://www.opengis.net/spec/owc/1.0/req/wfs',
      outputFormats: ['application/json'], defaultCrs: 'EPSG:4326',
      operations: [{ code: 'GetFeature', method: 'GET', href: 'https://example.org/wfs?TYPENAMES=roads' }],
    }];
    const features = [
      new OWSResource({ title: 'WFS', updated: '', folder: '/0', active: false, offerings: [{ code: offerings[0].code }] }),
      new OWSResource({ title: 'Roads', updated: '', folder: '/0/0', active: false, offerings }),
      new OWSResource({ title: 'Rivers', updated: '', folder: '/0/1', active: false, offerings }),
    ];
    render(<AdminContext><OwsContextBase initialFeatures={features}>
      <LayerTree initialExpanded={['/0']} /><ContextProbe />
    </OwsContextBase></AdminContext>);

    const checkboxes = (title: string) => within(screen.getByText(title, { selector: 'p' }).closest('.MuiTreeItem-label') as HTMLElement).getAllByRole('checkbox');
    expect(checkboxes('Roads')[1]).not.toBeChecked();
    expect(checkboxes('Roads')).toHaveLength(2);
    expect(checkboxes('Roads')[0]).toBeDisabled();
    fireEvent.click(checkboxes('Roads')[1]);
    expect(checkboxes('Roads')[1]).toBeChecked();
    expect(checkboxes('Rivers')[1]).not.toBeChecked();
    expect(checkboxes('WFS')[1]).toHaveAttribute('data-indeterminate', 'true');
    expect(screen.getByTestId('wfs-requests')).toHaveTextContent(/^Roads$/);

    fireEvent.click(screen.getByRole('button', { name: 'Reload context' }));
    expect(checkboxes('Roads')[1]).toBeChecked();
    fireEvent.click(checkboxes('Rivers')[1]);
    expect(checkboxes('WFS')[1]).toBeChecked();
    expect(checkboxes('WFS')[1]).toHaveAttribute('data-indeterminate', 'false');

    fireEvent.click(checkboxes('WFS')[1]);
    expect(checkboxes('Roads')[1]).not.toBeChecked();
    expect(checkboxes('Rivers')[1]).not.toBeChecked();
    expect(screen.getByTestId('wfs-requests')).toBeEmptyDOMElement();
    fireEvent.click(checkboxes('WFS')[1]);
    expect(checkboxes('Roads')[1]).toBeChecked();
    expect(checkboxes('Rivers')[1]).toBeChecked();
    expect(screen.getByTestId('wfs-requests')).toHaveTextContent('Roads,Rivers');
  });

  it('toggles raster and vector independently through folders containing WMS and WFS', () => {
    const features = [
      new OWSResource({ title: 'Mixed folder', updated: '', folder: '/0' }),
      new OWSResource({ title: 'Nested folder', updated: '', folder: '/0/0' }),
      new OWSResource({
        title: 'WMS layer', updated: '', folder: '/0/0/0',
        offerings: [{
          code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
          operations: [
            { code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=roads', active: false },
            { code: 'GetFeatureInfo', method: 'GET', href: 'https://example.org/wms?QUERY_LAYERS=roads', active: false },
          ],
        }],
      }),
      new OWSResource({
        title: 'WFS layer', updated: '', folder: '/0/0/1', active: false,
        offerings: [{
          code: 'http://www.opengis.net/spec/owc/1.0/req/wfs',
          outputFormats: ['application/json'], defaultCrs: 'EPSG:4326',
          operations: [{ code: 'GetFeature', method: 'GET', href: 'https://example.org/wfs?TYPENAMES=roads' }],
        }],
      }),
    ];
    render(<AdminContext><OwsContextBase initialFeatures={features}>
      <LayerTree initialExpanded={['/0', '/0/0']} /><ContextProbe />
    </OwsContextBase></AdminContext>);

    const controls = (title: string) => within(screen.getByText(title, { selector: 'p' }).closest('.MuiTreeItem-label') as HTMLElement);
    const raster = (title: string) => controls(title).getByRole('checkbox', { name: 'LayerTree.raster' });
    const vector = (title: string) => controls(title).getByRole('checkbox', { name: 'LayerTree.vector' });
    for (const title of ['Mixed folder', 'Nested folder', 'WMS layer', 'WFS layer']) {
      expect(controls(title).getAllByRole('checkbox')).toHaveLength(2);
    }
    expect(raster('WFS layer')).toBeDisabled();
    expect(raster('Mixed folder')).toBeEnabled();
    expect(vector('Mixed folder')).toBeEnabled();

    fireEvent.click(raster('Mixed folder'));
    expect(raster('WMS layer')).toBeChecked();
    expect(raster('Nested folder')).toBeChecked();
    expect(vector('WMS layer')).not.toBeChecked();
    expect(vector('WFS layer')).not.toBeChecked();
    expect(screen.getByTestId('wfs-requests')).toBeEmptyDOMElement();

    fireEvent.click(vector('WFS layer'));
    expect(vector('Mixed folder')).toHaveAttribute('data-indeterminate', 'true');
    expect(vector('Nested folder')).toHaveAttribute('data-indeterminate', 'true');
    expect(vector('WMS layer')).not.toBeChecked();
    expect(raster('WMS layer')).toBeChecked();

    fireEvent.click(vector('Mixed folder'));
    expect(vector('WMS layer')).toBeChecked();
    expect(vector('WFS layer')).toBeChecked();
    expect(vector('Mixed folder')).toBeChecked();
    expect(vector('Mixed folder')).toHaveAttribute('data-indeterminate', 'false');
    expect(screen.getByTestId('wfs-requests')).toHaveTextContent(/^WFS layer$/);

    fireEvent.click(raster('Nested folder'));
    expect(raster('Mixed folder')).not.toBeChecked();
    expect(raster('WMS layer')).not.toBeChecked();
    expect(vector('WMS layer')).toBeChecked();
    expect(vector('WFS layer')).toBeChecked();

    fireEvent.click(vector('WMS layer'));
    expect(vector('Mixed folder')).toHaveAttribute('data-indeterminate', 'true');
    expect(vector('WFS layer')).toBeChecked();
    fireEvent.click(vector('Mixed folder'));
    expect(vector('WMS layer')).toBeChecked();
    fireEvent.click(vector('Mixed folder'));
    expect(vector('WMS layer')).not.toBeChecked();
    expect(vector('WFS layer')).not.toBeChecked();
    expect(screen.getByTestId('wfs-requests')).toBeEmptyDOMElement();
  });

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

  it('blends a layer which advertises neither styles nor dimensions', async () => {
    const feature = new OWSResource({
      title: 'Plain layer', updated: '', folder: '/0', active: true,
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        operations: [{ code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a' }],
      }],
    });
    render(<AdminContext><OwsContextBase initialFeatures={[feature]}><LayerTree /></OwsContextBase></AdminContext>);

    // the panel is there for every layer the viewer can draw, even one with nothing else to edit
    await openStyleControls();
    const slider = screen.getByRole('slider', { name: 'viewerControls.opacity' });
    expect(slider).toHaveValue('100');
    expect(slider).toHaveAttribute('aria-valuetext', 'viewerControls.opacityValue');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();

    fireEvent.change(slider, { target: { value: '40' } });
    // the viewer session holds the new blending of this layer alone
    expect(opacityState['/0']).toBe(0.4);
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
    const leafRow = screen.getByText('buildings', { selector: 'p' }).closest('.MuiTreeItem-label') as HTMLElement;
    fireEvent.click(within(leafRow).getAllByRole('checkbox')[1]);

    // The imported folders are normalized; WFS activation belongs to the vector column.
    expect(within(leafRow).getAllByRole('checkbox')[1]).toBeChecked();
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

  it('activates a WFS type through the vector checkbox and disables its raster checkbox', () => {
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

    // Every row carries raster and vector checkboxes, even when raster is unavailable.
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(4);
    expect(checkboxes[2]).toBeDisabled();
    expect(screen.getByTestId('leaf-active')).toHaveTextContent('false');

    fireEvent.click(checkboxes[3]);

    expect(screen.getByTestId('leaf-active')).toHaveTextContent('true');
    // the group of a fully active subtree answers active as well
    expect(screen.getByTestId('root-active')).toHaveTextContent('true');

    // react-admin hands the same input element over to the re-rendered row, so its checked
    // property is stale after the activation - the tree's second row is asked for the leaf again
    fireEvent.click(screen.getAllByRole('checkbox')[3]);

    expect(screen.getByTestId('leaf-active')).toHaveTextContent('false');
  });
});

// what a viewer session keeps per layer, just like the real provider does
const opacityState: Record<string, number> = {};
const viewerState: {
  mapLoading: { failedFeatures: unknown[], errors: unknown[] };
  scaleDenominator?: number;
  opacityOf: (features: OWSResource[]) => number;
  setLayerOpacity: (folder: string, opacity: number) => void;
} = {
  mapLoading: { failedFeatures: [], errors: [] },
  scaleDenominator: undefined,
  opacityOf: (features: OWSResource[]) =>
    opacityState[features[0]?.properties.folder ?? ''] ?? 1,
  setLayerOpacity: (folder: string, opacity: number) => {
    opacityState[folder] = opacity;
  },
};

vi.mock("../MapViewer/MapViewerBase", () => ({ useMapViewerBase: () => viewerState }));
