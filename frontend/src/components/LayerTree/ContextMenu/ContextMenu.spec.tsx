import type { OfferingDimension } from '../../../ows-lib/OwsContext/types';

import { AdminContext } from 'react-admin';

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OWSResource } from '../../../ows-lib/OwsContext/core';
import { OwsContextBase, useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import LayerTree from '../LayerTree';

// the viewer context as a small subscription store: tests update it the way the real MapViewerBase
// would, and every consumer of the hook re-renders with it
const mapState = vi.hoisted(() => ({
  map: undefined as undefined | { getContainer: () => HTMLElement; invalidateSize: ReturnType<typeof vi.fn>; panTo: ReturnType<typeof vi.fn> },
  displayedTimes: {} as Record<string, string>,
  animation: undefined as undefined | { folder: string; fps: number; loop: boolean },
  failedFeatures: [] as { properties: { folder?: string } }[],
  update: undefined as undefined | ((patch: Record<string, unknown>) => void),
}));
beforeEach(() => {
  mapState.map = undefined;
  mapState.displayedTimes = {};
  mapState.animation = undefined;
  mapState.failedFeatures = [];
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const wmsOperations = (active: boolean, dimensions?: OfferingDimension[]) => [{
  code: 'http://www.opengis.net/spec/owc/1.0/req/wms',
  ...(dimensions !== undefined && { dimensions }),
  operations: [
    { code: 'GetMap', method: 'GET', href: 'https://example.org/wms?LAYERS=a', active },
    { code: 'GetFeatureInfo', method: 'GET', href: 'https://example.org/wms?LAYERS=a&QUERY_LAYERS=a', active },
  ],
}];

const testFeatures = () => [
  new OWSResource({ title: 'group', updated: '', folder: '/0' }, 'group'),
  new OWSResource({ title: 'first', updated: '', folder: '/0/0', active: true, offerings: wmsOperations(true, [
    { name: 'elevation', values: '0,10,20', default: '10' },
    { name: 'DIM_sensor', values: '0/100/10' },
    { name: 'time', units: 'ISO8601', values: '2025-04-01/2026-10-01/P1D' },
  ]) }, 'first'),
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
        mapHref: feature.getWmsOperationByCode('GetMap')?.href ?? null,
        infoHref: feature.getWmsOperationByCode('GetFeatureInfo')?.href ?? null,
      })))}
    </p>
  );
};

const renderTree = (features = testFeatures()) => render(
  <AdminContext>
    <OwsContextBase initialFeatures={features}>
      <LayerTree />
      <ContextProbe />
    </OwsContextBase>
  </AdminContext>
);

/** the option buttons of the tree labels, in tree order: group, first, second, other root */
const openMenuOf = (index: number) => {
  fireEvent.click(screen.getAllByRole('button', { name: 'viewerStyles.options' })[index]);
};

/** the root group opens as the tree arrives; open it by its arrow when it is closed */
const expandGroup = () => {
  const groupRow = document.querySelector('[data-owscontext-folder="/0"]');
  if (groupRow !== null && groupRow.getAttribute('aria-expanded') !== 'true') {
    fireEvent.click(groupRow.querySelector(':scope > div svg[data-testid="KeyboardArrowRightIcon"]') as Element);
  }
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
    // the second root tree moves above the first one, its subtree moves along; the
    // option button is taken from that row, since the arrival of a tree opens its
    // groups and shifts the plain index order of the other rows
    fireEvent.click((document.querySelector('[data-owscontext-folder="/1"]') as HTMLElement)
      .querySelector('[aria-label="viewerStyles.options"]') as Element);
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
      { id: 'root2', folder: '/0', title: 'other root', map: null, mapHref: null, infoHref: null },
    ]);
  }, TEST_TIMEOUT);

  it('previews a drag without requests, commits on release and keeps a pinned timeline through reorder until removal', async () => {
    vi.stubGlobal('PointerEvent', MouseEvent);
    mapState.map = { getContainer: () => document.body, invalidateSize: vi.fn(), panTo: vi.fn() };
    renderTree(); expandGroup();
    // the panel opens for every renderable layer, so the row of the dragged one is asked for it
    const firstRow = document.querySelector('[data-owscontext-folder="/0/0"]') as HTMLElement;
    fireEvent.click(within(firstRow).getByRole('button', { name: 'viewerControls.edit' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // the panel carries the opacity of the layer next to its timeline, so the axis is named
    const slider = screen.getByRole('slider', { name: /^viewerDimensions.dimension/ });
    const track = slider.closest('.MuiSlider-root')!;
    vi.spyOn(track, 'getBoundingClientRect').mockReturnValue({ left:0,right:200,width:200,top:0,bottom:20,height:20,x:0,y:0,toJSON:()=>({}) });
    const before = positionOf('first').mapHref;
    fireEvent.pointerDown(track, { button:0,clientX:100,clientY:10 });
    fireEvent.pointerMove(document, { buttons:1,clientX:110,clientY:10 });
    expect(positionOf('first').mapHref).toBe(before);
    fireEvent.pointerUp(document, { clientX:110,clientY:10 });
    expect(positionOf('first').mapHref).toContain('TIME=');
    fireEvent.click(screen.getByRole('button', { name:'viewerControls.pin' }));
    const timeline = screen.getByRole('region', { name:'viewerControls.timeline' });
    fireEvent.click(within(screen.getByRole('region', { name:'viewerControls.edit' })).getByRole('button', { name:'ra.action.close' }));
    const selected = new URL(positionOf('first').mapHref).searchParams.get('TIME');
    fireEvent.click(within(timeline).getByRole('button', { name:'ra.navigation.next' }));
    const next = new URL(positionOf('first').mapHref).searchParams.get('TIME');
    expect(Date.parse(next!) - Date.parse(selected!)).toBe(86400000);
    expect(mapState.map.invalidateSize).not.toHaveBeenCalled();
    expect(mapState.map.panTo).not.toHaveBeenCalled();
    openMenuOf(1); fireEvent.click(await item('moveDown'));
    expect(screen.getByRole('region', { name:'viewerControls.timeline' })).toBeVisible();
    expect(positionOf('first').folder).toBe('/0/1');
    openMenuOf(2); fireEvent.click(await item('remove'));
    await waitFor(() => expect(screen.queryByRole('region', { name:'viewerControls.timeline' })).not.toBeInTheDocument());
  }, TEST_TIMEOUT);

  it('selects an instant, shows custom dimensions and resets to the server default', async () => {
    renderTree(); expandGroup(); openMenuOf(1);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'viewerDimensions.title' }, { timeout: 4000 }));
    const input = await screen.findByLabelText('viewerDimensions.dimension (ISO8601) · UTC', { selector: 'input[type=datetime-local]' });
    fireEvent.change(input, { target: { value: '2025-04-02T00:00' } });
    fireEvent.blur(input);
    expect(positionOf('first').mapHref).toContain('TIME=2025-04-02T00%3A00%3A00.000Z');
    expect(positionOf('first').infoHref).toContain('TIME=2025-04-02T00%3A00%3A00.000Z');
    expect(document.querySelector('[aria-label="viewerDimensions.custom"]')).toBeInTheDocument();
    const updated = screen.getByLabelText('viewerDimensions.dimension (ISO8601) · UTC', { selector: 'input[type=datetime-local]' });
    fireEvent.change(updated, { target: { value: '2025-04-02T12:00' } }); fireEvent.blur(updated);
    expect(await screen.findByText('viewerDimensions.invalid')).toBeInTheDocument();
    expect(positionOf('first').mapHref).not.toContain('T12');
    fireEvent.click(screen.getByRole('button', { name: 'viewerDimensions.serverDefault' }));
    expect(positionOf('first').mapHref).not.toContain('TIME=');
    expect(document.querySelector('[aria-label="viewerDimensions.custom"]')).toBeNull();
  }, TEST_TIMEOUT);

  it('applies an advertised dimension value to both operations and refuses values the service does not offer', async () => {
    renderTree();
    expandGroup();
    openMenuOf(1);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'viewerDimensions.title' }, { timeout: 4000 }));

    // the list dimension offers the advertised values, the range dimension asks for a validated number
    const select = await screen.findByRole('combobox', { name: /viewerDimensions\.dimension/ });
    expect(select).toHaveValue('10');
    fireEvent.change(select, { target: { value: '20' } });
    expect(positionOf('first').mapHref).toContain('ELEVATION=20');
    expect(positionOf('first').infoHref).toContain('ELEVATION=20');

    const range = screen.getByRole('spinbutton');
    fireEvent.change(range, { target: { value: '155' } });
    expect(await screen.findByText('viewerDimensions.invalid')).toBeInTheDocument();
    expect(positionOf('first').mapHref).not.toContain('DIM_SENSOR=155');

    fireEvent.change(range, { target: { value: '50' } });
    expect(positionOf('first').mapHref).toContain('DIM_SENSOR=50');
  }, TEST_TIMEOUT);
});

// Playback keeps the map whole: it follows the advertised times, waits for the frame of a selected
// time to reach the map before advancing, steps over frames the service refuses, and stops at the
// end of the range unless looping was asked for (#705).
describe('time animation', () => {
  /** a layer whose advertised time is a short list, so the end of the range stays near */
  const frameFeatures = () => [
    new OWSResource({ title: 'group', updated: '', folder: '/0' }, 'group'),
    new OWSResource({ title: 'frames', updated: '', folder: '/0/0', active: true, offerings: wmsOperations(true, [
      { name: 'time', units: 'ISO8601', values: '2026-01-01,2026-01-02,2026-01-03' },
    ]) }, 'frames'),
  ];

  /** opens the control panel of the first layer and returns its region */
  let tree: ReturnType<typeof renderTree>;
  const openPanel = (features = testFeatures()) => {
    tree = renderTree(features);
    expandGroup();
    const row = document.querySelector('[data-owscontext-folder="/0/0"]') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'viewerControls.edit' }));
    return screen.getByRole('region', { name: 'viewerControls.edit' });
  };
  const timeOf = (title: string) =>
    new URL(positionOf(title).mapHref).searchParams.get('TIME');
  const play = (panel: HTMLElement) =>
    within(panel).getByRole('button', { name: 'viewerDimensions.play' });
  const pause = (panel: HTMLElement) =>
    within(panel).getByRole('button', { name: 'viewerDimensions.pause' });

  it('advances through the advertised times and waits for each frame to be drawn', () => {
    const panel = openPanel();
    // an earlier observation is on the map when playback starts
    act(() => mapState.update!({ displayedTimes: { '/0/0': '2025-03-31T00:00:00.000Z' } }));
    vi.useFakeTimers();
    fireEvent.click(play(panel));
    fireEvent.change(within(panel).getByRole('combobox', { name: 'viewerDimensions.speed' }), { target: { value: '4' } });

    // the first tick selects the first advertised observation
    act(() => vi.advanceTimersByTime(250));
    expect(timeOf('first')).toBe('2025-04-01T00:00:00.000Z');

    // its frame has not reached the map: playback holds on pace instead of queuing requests
    act(() => vi.advanceTimersByTime(1500));
    expect(timeOf('first')).toBe('2025-04-01T00:00:00.000Z');

    // once the map draws it, playback continues with the next advertised instant
    act(() => mapState.update!({ displayedTimes: { '/0/0': '2025-04-01T00:00:00.000Z' } }));
    act(() => vi.advanceTimersByTime(250));
    expect(timeOf('first')).toBe('2025-04-02T00:00:00.000Z');
    vi.useRealTimers();
  }, TEST_TIMEOUT);

  it('stops at the end of the advertised range and returns to its start when looping', () => {
    const panel = openPanel(frameFeatures());
    vi.useFakeTimers();
    fireEvent.click(play(panel));
    fireEvent.change(within(panel).getByRole('combobox', { name: 'viewerDimensions.speed' }), { target: { value: '4' } });
    act(() => vi.advanceTimersByTime(750));
    expect(timeOf('frames')).toBe('2026-01-03');

    // end of range: playback stopped there and the button offers to start again
    act(() => vi.advanceTimersByTime(1000));
    expect(timeOf('frames')).toBe('2026-01-03');
    expect(play(panel)).toBeInTheDocument();

    // with looping the same playback wraps around to the first observation
    fireEvent.click(play(panel));
    fireEvent.click(within(panel).getByRole('button', { name: 'viewerDimensions.loop' }));
    act(() => vi.advanceTimersByTime(500));
    expect(timeOf('frames')).toBe('2026-01-01');
    vi.useRealTimers();
  }, TEST_TIMEOUT);

  it('steps over a frame the service refuses instead of waiting for it forever', () => {
    const panel = openPanel(frameFeatures());
    vi.useFakeTimers();
    fireEvent.click(play(panel));
    fireEvent.change(within(panel).getByRole('combobox', { name: 'viewerDimensions.speed' }), { target: { value: '4' } });
    act(() => vi.advanceTimersByTime(250));
    expect(timeOf('frames')).toBe('2026-01-01');

    // the service refused that frame: the animation does not hold on it, it moves onward
    act(() => mapState.update!({ failedFeatures: [{ properties: { folder: '/0/0' } }] }));
    act(() => vi.advanceTimersByTime(250));
    expect(timeOf('frames')).toBe('2026-01-02');

    // pausing at a refused frame and starting again steps over it right away
    fireEvent.click(pause(panel));
    fireEvent.click(play(panel));
    expect(timeOf('frames')).toBe('2026-01-03');
    vi.useRealTimers();
  }, TEST_TIMEOUT);

  it('ends the animation together with the control which played it', () => {
    const panel = openPanel(frameFeatures());
    vi.useFakeTimers();
    fireEvent.click(play(panel));
    act(() => vi.advanceTimersByTime(500));
    expect(mapState.animation).toBeDefined();

    // closing the panel takes the control away, and the animation ends with it
    tree.unmount();
    expect(mapState.animation).toBeUndefined();
    vi.useRealTimers();
  }, TEST_TIMEOUT);
});

vi.mock('../../MapViewer/MapViewerBase', async () => {
  const { useSyncExternalStore } = await import('react');
  const listeners = new Set<() => void>();
  let revision = 0;
  const subscribe = (notify: () => void) => {
    listeners.add(notify);
    return () => { listeners.delete(notify); };
  };
  mapState.update = (patch) => {
    Object.assign(mapState, patch);
    revision += 1;
    listeners.forEach((notify) => notify());
  };
  return {
    useMapViewerBase: () => {
      useSyncExternalStore(subscribe, () => revision);
      return {
        mapLoading: { status: 'idle', loaded: 0, total: 0, errors: [], timings: {}, failedFeatures: mapState.failedFeatures },
        map: mapState.map,
        opacityOf: () => 1,
        setLayerOpacity: () => undefined,
        displayedTimes: mapState.displayedTimes,
        setDisplayedTime: (folder: string, time: string | undefined) => mapState.update!({
          displayedTimes: time === undefined
            ? Object.fromEntries(Object.entries(mapState.displayedTimes).filter(([key]) => key !== folder))
            : { ...mapState.displayedTimes, [folder]: time },
        }),
        animation: mapState.animation,
        setAnimation: (animation: typeof mapState.animation) => mapState.update!({ animation }),
      };
    },
  };
});
