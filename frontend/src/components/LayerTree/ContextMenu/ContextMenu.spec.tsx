import { AdminContext } from 'react-admin';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OWSResource } from '../../../ows-lib/OwsContext/core';
import { OwsContextBase, useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import LayerTree from '../LayerTree';

const wmsOperations = (active: boolean) => [{
  code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
  operations: [
    { code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a', active },
    { code: 'GetFeatureInfo', method: 'GET', href: 'https://example.org/wms?LAYERS=a&QUERY_LAYERS=a', active },
  ],
}];

const testFeatures = () => [
  new OWSResource({ title: 'group', updated: '', folder: '/0' }, 'group'),
  new OWSResource({ title: 'first', updated: '', folder: '/0/0', active: true, offerings: wmsOperations(true) }, 'first'),
  new OWSResource({ title: 'second', updated: '', folder: '/0/1', active: false, offerings: wmsOperations(false) }, 'second'),
  new OWSResource({ title: 'other root', updated: '', folder: '/1' }, 'root2'),
];

const ContextProbe = () => {
  const { owsContext } = useOwsContextBase();
  return (
    <p data-testid="context">
      {JSON.stringify(owsContext.features.map(feature => ({
        id: feature.id,
        folder: feature.properties.folder,
        title: feature.properties.title,
        map: feature.getWmsOperationByCode('GetMap')?.active ?? null,
      })))}
    </p>
  );
};

const renderTree = () => render(
  <AdminContext>
    <OwsContextBase initialFeatures={testFeatures()}>
      <LayerTree />
      <ContextProbe />
    </OwsContextBase>
  </AdminContext>
);

/** the option buttons of the tree labels, in tree order: group, first, second, other root */
const openMenuOf = (index: number) => {
  fireEvent.click(screen.getAllByRole('button', { name: 'viewerStyles.options' })[index]);
};

const expandGroup = () => {
  fireEvent.click(screen.getByTestId('KeyboardArrowRightIcon'));
};

const closeMenu = () => {
  const backdrop = document.querySelector('.MuiBackdrop-root');
  if (backdrop !== null) fireEvent.click(backdrop);
};

// the menu mounts in a portal; under the load of a full suite run, give it time to appear
const item = (key: string) =>
  screen.findByRole('menuitem', { name: `LayerTree.ContextMenu.${key}` }, { timeout: 4000 });

const context = () => JSON.parse(screen.getByTestId('context').textContent ?? '[]');

const positionOf = (title: string) =>
  context().find((feature: { title: string }) => feature.title === title);

const TEST_TIMEOUT = 20000;

describe('layer tree context menu', () => {
  it('moves a layer up over its previous sibling and keeps ids, order and activations', async () => {
    renderTree();
    expandGroup();
    openMenuOf(2);
    fireEvent.click(await item('moveUp'));

    // the two children swapped their positions; ids and independent activations stayed with them
    expect(positionOf('second')).toMatchObject({ id: 'second', folder: '/0/0', map: false });
    expect(positionOf('first')).toMatchObject({ id: 'first', folder: '/0/1', map: true });
  }, TEST_TIMEOUT);

  it('moves a layer down over its next sibling', async () => {
    renderTree();
    expandGroup();
    openMenuOf(1);
    fireEvent.click(await item('moveDown'));

    expect(positionOf('first')).toMatchObject({ id: 'first', folder: '/0/1' });
    expect(positionOf('second')).toMatchObject({ id: 'second', folder: '/0/0' });
  }, TEST_TIMEOUT);

  it('disables the boundary moves of the first and the last sibling', async () => {
    renderTree();
    expandGroup();

    openMenuOf(1);
    expect(await item('moveUp')).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(await item('moveUp'));
    expect(positionOf('first')).toMatchObject({ folder: '/0/0' });
    closeMenu();

    openMenuOf(2);
    expect(await item('moveDown')).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(await item('moveDown'));
    expect(positionOf('second')).toMatchObject({ folder: '/0/1' });
  }, TEST_TIMEOUT);

  it('moves a whole group with its children when a root tree is reordered', async () => {
    renderTree();
    // the second root tree moves above the first one, its subtree moves along
    openMenuOf(1);
    expect(await item('moveUp')).not.toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(await item('moveUp'));

    expect(positionOf('other root')).toMatchObject({ id: 'root2', folder: '/0' });
    expect(positionOf('group')).toMatchObject({ id: 'group', folder: '/1' });
    expect(positionOf('first')).toMatchObject({ id: 'first', folder: '/1/0' });
    expect(positionOf('second')).toMatchObject({ id: 'second', folder: '/1/1' });
  }, TEST_TIMEOUT);

  it('removes a layer and keeps the remaining ids, grouping and activations', async () => {
    renderTree();
    expandGroup();
    openMenuOf(1);
    fireEvent.click(await item('remove'));

    const remaining = context();
    expect(remaining.map((feature: { id: string }) => feature.id))
      .toEqual(['group', 'second', 'root2']);
    // the gap left behind is renumbered, the sibling keeps its independent activations
    expect(positionOf('second')).toMatchObject({ id: 'second', folder: '/0/0', map: false });
  }, TEST_TIMEOUT);

  it('removes a group with its whole subtree', async () => {
    renderTree();
    openMenuOf(0);
    fireEvent.click(await item('remove'));

    expect(context()).toEqual([
      { id: 'root2', folder: '/0', title: 'other root', map: null },
    ]);
  }, TEST_TIMEOUT);
});

vi.mock('../../MapViewer/MapViewerBase', () => ({
  useMapViewerBase: () => ({ mapLoading: { failedFeatures: [], errors: [] }, map: undefined }),
}));
