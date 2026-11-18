import type { CrudEvent } from '../../providers/dataProvider';

import type { ReactNode } from 'react';
import { ReadyState } from 'react-use-websocket';

import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  RESOURCE_TOPIC,
  processTopic,
} from '../Resource/BackgroundProcess/JobCenter/BackgroundJobCenterContext';
import MyLayout from './Layout';

// a fake realtime bus: callbacks registered per topic, an emit() to push events
const bus = vi.hoisted(() => ({
  subs: new Map<string, Set<(event: CrudEvent) => void>>(),
}));

const state = vi.hoisted(() => ({
  // the two api windows the Background Job Center hydrates from
  active: {
    data: [] as { id: number; status: string; progress?: number }[],
    refetch: vi.fn(),
  },
  terminal: {
    data: [] as { id: number; status: string; progress?: number }[],
    refetch: vi.fn(),
  },
  notify: vi.fn(),
}));

// the drawer of the Background Job Center (#1206): a counting stand-in proves
// the center mounted without its rows joining this tree
const jobCenterMounts = vi.hoisted(() => vi.fn());

// the permission-lost bridge of #834: mounting is what this spec proves, its
// behavior is the bridge's own spec
const permissionLostHooks = vi.hoisted(() => ({
  refresh: vi.fn(),
  invalidateQueries: vi.fn(),
}));

// the react-admin surface the layout and the background-job stack use; the
// center, its store and the thin bridge run unmocked, so the wiring is the
// one shipping
vi.mock('react-admin', () => {
  // one dataProvider with one identity: react-admin hands out a stable
  // context value, and a fresh object per render would (rightfully) make
  // every subscription effect rebuild
  const provider = {
    subscribe: (topic: string, callback: (event: CrudEvent) => void) => {
      const set = bus.subs.get(topic) ?? new Set();
      set.add(callback);
      bus.subs.set(topic, set);
      return Promise.resolve({ data: null });
    },
    unsubscribe: (topic: string, callback: (event: CrudEvent) => void) => {
      bus.subs.get(topic)?.delete(callback);
      return Promise.resolve({ data: null });
    },
  };
  return {
    Layout: ({ children }: { children?: ReactNode }) => (
      <div data-testid="layout">{children}</div>
    ),
    useSidebarState: () => [false, vi.fn()],
    useRefresh: () => permissionLostHooks.refresh,
    useDataProvider: () => provider,
    useGetList: (_resource: string, params: { filter: { status: string } }) =>
      params.filter.status === 'pending,running' ? state.active : state.terminal,
    useNotify: () => state.notify,
    useTranslate: () => (key: string) => key,
  };
});

// the bridge's other hook: only the mount matters here, and no provider
// instance joins this tree
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: permissionLostHooks.invalidateQueries }),
}));

// the layout chrome: real enough to prove the mount order, light enough to not
// fetch the system status or build the menu
vi.mock('../../context/SystemStatusContext', () => ({
  SystemStatusProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));
vi.mock('../../context/HttpClientContext', () => ({
  useHttpClientContext: () => ({ realtimeIsReady: ReadyState.OPEN }),
}));
vi.mock('../../jsonapi/components/I18Observer', () => ({ default: () => null }));
vi.mock('../../jsonapi/components/Realtime/RealtimeBus', () => ({ default: () => null }));
vi.mock('../Resource/BackgroundProcess/JobCenter/JobCenterDrawer', () => ({
  default: () => {
    jobCenterMounts();
    return null;
  },
}));
vi.mock('./AppBar', () => ({ default: () => null }));
vi.mock('./Menu', () => ({ default: () => null }));
vi.mock('./BreadCrump', () => ({ default: () => null }));
vi.mock('./Footer', () => ({ default: () => null }));

const emit = (topic: string, event: CrudEvent) =>
  act(() => {
    bus.subs.get(topic)?.forEach((callback) => callback(event));
  });

// run the bridge's notify aggregation window inside act()
const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

const topicSize = (topic: string) => bus.subs.get(topic)?.size ?? 0;

beforeEach(() => {
  bus.subs.clear();
  state.active = { data: [], refetch: vi.fn() };
  state.terminal = { data: [], refetch: vi.fn() };
  state.notify = vi.fn();
  jobCenterMounts.mockClear();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('MyLayout', () => {
  it('mounts the background-job bridge, which notifies on failure', () => {
    render(
      <MyLayout>
        <span data-testid="content" />
      </MyLayout>,
    );
    expect(screen.getByTestId('layout')).toBeTruthy();
    expect(screen.getByTestId('content')).toBeTruthy();
    // the center's resource wide subscription is on the bus
    expect(topicSize(RESOURCE_TOPIC)).toBe(1);

    // a process created running is picked up from the bus and gets its own topic
    emit(RESOURCE_TOPIC, {
      type: 'created',
      payload: { ids: [41], records: [{ id: 41, status: 'running', progress: 0 }] },
    });
    expect(topicSize(processTopic(41))).toBe(1);

    // its failure arrives on that topic and becomes one aggregated notification
    emit(processTopic(41), {
      type: 'updated',
      payload: { ids: [41], records: [{ id: 41, status: 'failed' }] },
    });
    advance(1000); // the bridge's notify aggregation window
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith('backgroundJobs.notification.failedOne', {
      type: 'error',
    });
  });

  it('mounts one subscription per topic per mount (#1461)', () => {
    // the convergence: before it, Layout mounted the center and the bridge as
    // two stores with two subscription sets, so every topic below carried two
    // callbacks and every event was folded twice
    state.active.data = [
      { id: 1, status: 'running', progress: 10 },
      { id: 2, status: 'running', progress: 20 },
    ];
    render(
      <MyLayout>
        <span data-testid="content" />
      </MyLayout>,
    );
    // the resource wide topic: one callback, not one per mounted store
    expect(topicSize(RESOURCE_TOPIC)).toBe(1);
    // every watched process topic: exactly the center's single callback
    expect(topicSize(processTopic(1))).toBe(1);
    expect(topicSize(processTopic(2))).toBe(1);

    // the delta diffing belongs to the one survivor: when a process finishes
    // only its own topic goes away, and it goes away completely
    emit(processTopic(1), {
      type: 'updated',
      payload: { ids: [1], records: [{ id: 1, status: 'completed', progress: 100 }] },
    });
    expect(topicSize(processTopic(1))).toBe(0);
    expect(topicSize(processTopic(2))).toBe(1);
    expect(topicSize(RESOURCE_TOPIC)).toBe(1);
  });

  it('mounts the Background Job Center around the layout', () => {
    render(
      <MyLayout>
        <span />
      </MyLayout>,
    );
    expect(jobCenterMounts).toHaveBeenCalled();
    // the legacy per-event snackbar observer retired with notistack (#1203):
    // there is no module left to mount, the bridge is the notification
    // path — so this spec can no longer stand one in, it can only pin the
    // bridge and the center
  });
});
