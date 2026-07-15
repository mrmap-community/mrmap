import { ReactNode } from 'react';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { OWSResource } from '../../ows-lib/OwsContext/core';
import { karteRpFeatures as testdata } from '../../ows-lib/OwsContext/tests/data';
import { OwsContextBase, useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase';
import LayerTree from './LayerTree';


const getKarteRpFeatures = () => {
  return testdata.map(resource => new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry));
}

const MapViewerBaseWrapper = ({ children }: { children: ReactNode }) => {
  return (
    <OwsContextBase initialFeatures={getKarteRpFeatures()}>
      {children}
    </OwsContextBase>
  )
}


const ContextProbe = () => {
  const { owsContext } = useOwsContextBase();
  const target = owsContext.findResourceByFolder('/0');
  const getMapOperation = target?.getWmsOperationByCode('GetMap');
  const getFeatureInfoOperation = target?.getWmsOperationByCode('GetFeatureInfo');

  return (
    <div>
      <span data-testid="get-map-state">{String(getMapOperation?.active ?? false)}</span>
      <span data-testid="get-feature-info-state">{String(getFeatureInfoOperation?.active ?? false)}</span>
    </div>
  );
};

describe('LayerTree', () => {
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

  it('toggles GetFeatureInfo via the second checkbox', () => {
    const customFeatures = [new OWSResource({
      title: 'Test Layer',
      folder: '/0',
      offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        operations: [
          { code: 'GetMap', active: false },
          { code: 'GetFeatureInfo', active: false },
        ],
      }],
    })];

    render(
      <OwsContextBase initialFeatures={customFeatures}>
        <LayerTree />
        <ContextProbe />
      </OwsContextBase>
    );

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);

    expect(screen.getByTestId('get-feature-info-state')).toHaveTextContent('true');
  });

  it('renders GetMap checkbox as indeterminate when descendants are mixed active', () => {
    const customFeatures = [
      new OWSResource({
        title: 'Parent Layer',
        folder: '/0',
        offerings: [{
          code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
          operations: [
            { code: 'GetMap', active: true },
          ],
        }],
      }),
      new OWSResource({
        title: 'Child Layer',
        folder: '/0/1',
        offerings: [{
          code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
          operations: [
            { code: 'GetMap', active: false },
          ],
        }],
      }),
    ];

    render(
      <OwsContextBase initialFeatures={customFeatures}>
        <LayerTree />
      </OwsContextBase>
    );

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[0]).toHaveProperty('indeterminate', true);
  });
});