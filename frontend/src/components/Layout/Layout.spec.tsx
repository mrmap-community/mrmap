import type { CrudEvent } from '../../providers/dataProvider';

import type { ReactNode } from 'react';
import { ReadyState } from 'react-use-websocket';

import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  RESOURCE_TOPIC,
  processTopic,
} from '../Resource/BackgroundProcess/BackgroundJobBridge';
import MyLayout from './Layout';

// a fake realtime bus: callbacks registered per topic, an emit() to push events
const bus = vi.hoisted(() => ({
  subs: new Map<string, Set<(event: CrudEvent) => void>>(),
}));

const state = vi.hoisted(() => ({
  listData: [] as { id: number; status: string }[],
  refetch: vi.fn(),
  notify: vi.fn(),
}));

// the Background Job Center (#1203): a counting stand-in proves the mount
// without its store joining the bus or notifying in this spec
const jobCenterMounts = vi.hoisted(() => vi.fn());

// the react-admin surface the layout and the background-job bridge use; the
// bridge itself and its store run unmocked, so the wiring is the one shipping
vi.mock('react-admin', () => ({
  Layout: ({ children }: { children?: ReactNode }) => (
    <div data-testid="layout">{children}</div>
  ),
  useSidebarState: () => [false, vi.fn()],
  useDataProvider: () => ({
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
  }),
  useGetList: () => ({ data: state.listData, refetch: state.refetch }),
  useNotify: () => state.notify,
  useTranslate: () => (key: string) => key,
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
vi.mock('../Resource/BackgroundProcess/JobCenter/BackgroundJobCenterContext', () => ({
  default: ({ children }: { children?: ReactNode }) => {
    jobCenterMounts();
    return <>{children}</>;
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

// run the store's coalesced publish / notify windows inside act()
const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

const topicSize = (topic: string) => bus.subs.get(topic)?.size ?? 0;

beforeEach(() => {
  bus.subs.clear();
  state.listData = [];
  state.refetch.mockClear();
  state.notify.mockClear();
  jobCenterMounts.mockClear();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('MyLayout', () => {
  it('mounts the background-job bridge, which watches the bus and notifies on failure', () => {
    render(
      <MyLayout>
        <span data-testid="content" />
      </MyLayout>,
    );
    expect(screen.getByTestId('layout')).toBeTruthy();
    expect(screen.getByTestId('content')).toBeTruthy();
    // the renderless bridge subscribes the resource wide topic on the bus
    expect(topicSize(RESOURCE_TOPIC)).toBe(1);

    // a process created running is picked up from the bus and gets its own topic
    emit(RESOURCE_TOPIC, {
      type: 'created',
      payload: { ids: [41], records: [{ id: 41, status: 'running', progress: 0 }] },
    });
    advance(250); // the store's coalesced publish, then the bridge watches it
    expect(topicSize(processTopic(41))).toBe(1);

    // its failure arrives on that topic and becomes one aggregated notification
    emit(processTopic(41), {
      type: 'updated',
      payload: { ids: [41], records: [{ id: 41, status: 'failed' }] },
    });
    advance(1000); // the notify aggregation window
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith('backgroundJobs.notification.failedOne', {
      type: 'error',
    });
  });
  it('mounts the Background Job Center around the layout', () => {
    render(
      <MyLayout>
        <span />
      </MyLayout>,
    );
    expect(jobCenterMounts).toHaveBeenCalled();
    // the legacy per-event snackbar observer retired with notistack (#1203):
    // there is no module left to mount, the bridge above is the notification
    // path — so this spec can no longer stand one in, it can only pin the
    // bridge and the center
  });
});
