import { AdminContext } from 'react-admin';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OWSContext, OWSResource } from '../../../ows-lib/OwsContext/core';
import { OwsContextBase, useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import {
  DRAFT_STORAGE_KEY,
  SHARE_FRAGMENT_PARAMETER,
  MapTransferControls,
  decodeShareFragment,
  encodeShareFragment,
  serializeForTransfer,
} from './MapTransferControls';

const draftDocument = (title: string, layer: string, active: boolean) =>
  JSON.parse(serializeForTransfer(new OWSContext(undefined, [
    new OWSResource({ title: layer, updated: '2026-10-23T08:00:00Z', folder: '/0', active: true, offerings: [{
      code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
      operations: [
        { code: 'GetMap', method: 'GET', href: `https://example.org/wms?LAYERS=${layer}`, active },
        { code: 'GetFeatureInfo', method: 'GET', href: `https://example.org/wms?LAYERS=${layer}&QUERY_LAYERS=${layer}`, active },
      ],
    }] }, layer),
  ]),
  ));

const ContextProbe = () => {
  const { owsContext } = useOwsContextBase();
  return <p data-testid="context">{JSON.stringify({
    titles: owsContext.features.map(feature => feature.properties.title),
    authenticationHeaders: owsContext.authenticationHeaders?.length ?? 0,
  })}</p>;
};

const renderControls = (initialFeatures: OWSResource[] = []) => render(
  <AdminContext>
    <OwsContextBase initialFeatures={initialFeatures}>
      <MapTransferControls />
      <ContextProbe />
    </OwsContextBase>
  </AdminContext>
);

const probe = () => JSON.parse(screen.getByTestId('context').textContent ?? '{}');

describe('transfer serialization', () => {
  it('strips credentials, url secrets and the runtime lookup but keeps the round trip', () => {
    const context = new OWSContext(undefined, [
      new OWSResource({ title: 'protected', updated: '', folder: '/0', offerings: [{
        code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
        operations: [
          { code: 'GetMap', method: 'GET', href: 'https://user:secret@example.org/wms?LAYERS=a&token=public', active: true },
        ],
      }] }, 'protected'),
    ]);
    context.authenticationHeaders = [{ id: 'auth-1', type: 'header', name: 'api', origin: 'example.org', value: 'top-secret' }];
    const serialized = serializeForTransfer(context);
    expect(serialized).not.toContain('top-secret');
    expect(serialized).not.toContain('user:secret');
    expect(serialized).not.toContain('folderToResource');
    expect(serialized).toContain('token=public');

    const reopened = OWSContext.fromPlainObject(JSON.parse(serialized));
    expect(reopened.features.map(feature => feature.properties.title)).toEqual(['protected']);
    expect(reopened.findResourceByFolder('/0')?.getWmsOperationByCode('GetMap')?.active).toBe(true);
  });

  it('round trips share fragments including non ascii content', () => {
    const payload = JSON.stringify({ title: 'Karte über Düsseldorf ✓' });
    const fragment = encodeShareFragment(payload);
    expect(fragment.slice(SHARE_FRAGMENT_PARAMETER.length + 1)).not.toMatch(/[+/=]/);
    expect(decodeShareFragment(`#${fragment}`)).toEqual({ title: 'Karte über Düsseldorf ✓' });
    expect(decodeShareFragment('#other=1')).toBeUndefined();
    expect(decodeShareFragment('#map=%%%broken%%%')).toBeUndefined();
  });
});

describe('map transfer controls', () => {
  const initialFeature = (title: string) => new OWSResource({
    title, updated: '', folder: '/0',
    offerings: [{ code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
      operations: [{ code: 'GetMap', method: 'GET', href: `https://example.org/wms?LAYERS=${title}`, active: true }] }],
  }, title);

  beforeEach(() => {
    window.localStorage.clear();
    window.location.hash = '';
  });

  it('exports the current document as a downloadable geojson file', () => {
    const createObjectURL = vi.fn(() => 'blob:mock') as unknown as ((blob: Blob) => string) & { mock: { calls: [[Blob]] } };
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = vi.fn();
    try {
      renderControls([initialFeature('first')]);

      fireEvent.click(screen.getByRole('button', { name: 'export-map' }));
      expect(createObjectURL).toHaveBeenCalledTimes(1);
      expect((createObjectURL.mock.calls[0][0] as Blob).type).toBe('application/geo+json');
      expect(probe().titles).toEqual(['first']);
    } finally {
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
    }
  });

  it('imports a document from a chosen file and reports the result', async () => {
    renderControls([initialFeature('first')]);
    const file = { name: 'map.geojson', text: async () => JSON.stringify(draftDocument('t', 'imported', true)) } as unknown as File;

    fireEvent.change(document.querySelector('input[type=file]')!, { target: { files: [file] } });
    expect(await screen.findByText('mapTransfer.importOk')).toBeInTheDocument();
    expect(probe().titles).toEqual(['imported']);
  });

  it('reports an invalid import without replacing the current map', async () => {
    renderControls([initialFeature('first')]);
    const file = { name: 'broken.json', text: async () => '{ not json' } as unknown as File;

    fireEvent.change(document.querySelector('input[type=file]')!, { target: { files: [file] } });
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(probe().titles).toEqual(['first']);
  });

  it('offers a share link that carries the document instead of a server id', async () => {
    renderControls([initialFeature('shared source')]);

    fireEvent.click(screen.getByRole('button', { name: 'share-map' }));
    const field = await screen.findByDisplayValue(/#map=/);
    const decoded = decodeShareFragment(`${String((field as HTMLTextAreaElement).value).split('#')[1]}`) as { features: { properties: { title: string } }[] };
    expect(decoded.features.map(feature => feature.properties.title)).toEqual(['shared source']);
  });

  it('opens a shared document from the location fragment and removes it', async () => {
    window.location.hash = encodeShareFragment(JSON.stringify(draftDocument('t', 'from share', true)));
    renderControls();

    await waitFor(() => expect(probe().titles).toEqual(['from share']));
    expect(window.location.hash).toBe('');
  });

  it('restores the draft of the last session on start', async () => {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draftDocument('t', 'drafted', true)));
    renderControls();

    await waitFor(() => expect(probe().titles).toEqual(['drafted']));
    expect(await screen.findByText('mapTransfer.restoredDraft')).toBeInTheDocument();
  });

  it('saves the current map into the draft storage after a pause', async () => {
    renderControls([initialFeature('autosaved')]);

    await waitFor(() => expect(window.localStorage.getItem(DRAFT_STORAGE_KEY)).toContain('autosaved'), { timeout: 3000 });
  });
});
