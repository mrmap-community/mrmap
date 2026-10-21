import { ReactNode } from 'react';

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OWSResource } from '../../ows-lib/OwsContext/core';
import { Position } from '../../ows-lib/OwsContext/enums';
import { karteRpFeatures as testdata } from '../../ows-lib/OwsContext/tests/data';
import { OwsContextBase, useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase';



const getKarteRpFeatures = () => {
  return testdata.map(resource => new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry));
}

export const MapViewerBaseWrapper = ({ children }: { children: ReactNode }) => {
  return (
    <OwsContextBase initialFeatures={getKarteRpFeatures()}>
      {children}
    </OwsContextBase>
  )
}


const TestingComponent = () => {
    const { owsContext, moveFeature } = useOwsContextBase();

    return (
      <div>
        {owsContext.features.map(feature => 
            <div 
                key={feature.properties.folder}
                data-testid='row'
            >
                {feature.properties.title}
            </div>
        )}
      
        <button data-testid={'move-left'} onClick={() => moveFeature(owsContext.features[10], owsContext.features[8], Position.left)}>move left</button>
        <button data-testid={'move-firstChild'} onClick={() => moveFeature(owsContext.features[10], owsContext.features[0], Position.firstChild)}>move first child</button>

      </div>
    );
  };
  

describe('OwsContextBase', () => {
  it('OwsContextBase test moveFeature sequences works without any errors', () => {
   render(<TestingComponent />, {wrapper: MapViewerBaseWrapper});

   fireEvent.click(screen.getByTestId('move-left'));
   const firstMoveResult = screen.getAllByTestId('row')
   expect(within(firstMoveResult[6]).queryByText('Wald')).toBeInTheDocument();
   expect(within(firstMoveResult[7]).queryByText('Wald 0')).toBeInTheDocument();
   expect(within(firstMoveResult[8]).queryByText('Wald 3')).toBeInTheDocument();
   expect(within(firstMoveResult[9]).queryByText('Wald 1')).toBeInTheDocument();
   expect(within(firstMoveResult[10]).queryByText('Wald 2')).toBeInTheDocument();


   fireEvent.click(screen.getByTestId('move-firstChild'));
   const secondMoveResult = screen.getAllByTestId('row')
   expect(within(secondMoveResult[1]).queryByText('Wald 2')).toBeInTheDocument();
   expect(within(secondMoveResult[2]).queryByText('Landesfläche')).toBeInTheDocument();

  });
 
});


describe('OwsContextBase document validation', () => {

  const ValidationTester = () => {
    const { owsContext, loadingStatus, updateOwsContext, initialFromOwsContext } = useOwsContextBase();

    return (
      <div>
        <span data-testid="status">{loadingStatus}</span>
        {owsContext.features.map(feature =>
          <div key={String(feature.id)} data-testid="row">{feature.properties.title}</div>
        )}
        <button
          data-testid={'apply-malformed'}
          onClick={() => updateOwsContext({ type: 'FeatureCollection', features: [] })}>
            apply malformed
        </button>
        <button
          data-testid={'import'}
          onClick={() => initialFromOwsContext('https://www.example.org/context/1/')}>
            import
        </button>
      </div>
    );
  };

  it('keeps the current context when updateOwsContext rejects a document', () => {
    render(<ValidationTester />, { wrapper: MapViewerBaseWrapper });

    fireEvent.click(screen.getByTestId('apply-malformed'));

    expect(screen.getByTestId('status')).toHaveTextContent('error');
    expect(screen.getAllByTestId('row')).toHaveLength(testdata.length);
  });

  it('keeps the current context when an imported document is malformed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ type: 'Feature', features: 'not an array' }),
      { status: 200 }
    )));

    render(<ValidationTester />, { wrapper: MapViewerBaseWrapper });

    fireEvent.click(screen.getByTestId('import'));

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('error'));
    expect(screen.getAllByTestId('row')).toHaveLength(testdata.length);

    vi.unstubAllGlobals();
  });

});

it('persists supplied capabilities authentication for subsequent same-origin WMS operations', async () => {
  const xml = await import('../../ows-lib/XMLParser/tests/capabilities_inherited_130.xml?raw');
  const fetch = vi.fn(async (_request: Request) => new Response(xml.default, { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  let current: ReturnType<typeof useOwsContextBase>;
  const Tester = () => {
    current = useOwsContextBase();
    return <button onClick={() => current.addWMSByUrl('https://example.com/wms', new Headers({ Authorization: 'Basic secret' }))}>append</button>;
  };
  render(<OwsContextBase><Tester /></OwsContextBase>);
  fireEvent.click(screen.getByRole('button', { name: 'append' }));
  await waitFor(() => expect(current.loadingStatus).toBe('ready'));
  const request = fetch.mock.calls[0][0] as unknown as Request;
  expect(request.headers.get('Authorization')).toBe('Basic secret');
  expect(request.redirect).toBe('error');
  expect(current!.owsContext.authenticationHeaders).toEqual([expect.objectContaining({ origin: 'https://example.com', value: 'Basic secret' })]);
  const operations = current!.owsContext.features.flatMap(feature => feature.getWmsOffering()?.operations ?? []);
  const capabilities = operations.filter(operation => operation.code === 'GetCapabilities');
  expect(capabilities.length).toBeGreaterThan(0);
  expect(capabilities.every(operation => operation['x-authentication-id'] === current!.owsContext.authenticationHeaders![0].id)).toBe(true);
  expect(operations.every(operation => typeof operation['x-authentication-id'] === 'string')).toBe(true);
  vi.unstubAllGlobals();
});
