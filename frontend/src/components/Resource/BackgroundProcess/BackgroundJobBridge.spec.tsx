import type { CrudEvent } from '../../../providers/dataProvider';

import type { RaRecord } from 'react-admin';

import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BackgroundJobBridge, {
  RESOURCE_TOPIC,
  processTopic,
} from './BackgroundJobBridge';
import { createBackgroundJobStore } from './jobsStore';

// a fake realtime bus: callbacks registered per topic, an emit() to push events
const bus = vi.hoisted(() => ({
  subs: new Map<string, Set<(event: CrudEvent) => void>>(),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
}));

const state = vi.hoisted(() => ({
  listData: [] as RaRecord[],
  refetch: vi.fn(),
  notify: vi.fn(),
  ready: 1, // ReadyState.OPEN
}));

// ReadyState is an enum: CONNECTING 0, OPEN 1, CLOSING 2, CLOSED 3
vi.mock('react-use-websocket', () => ({
  ReadyState: { UNINSTANTIATED: -1, CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 },
}));

vi.mock('../../../context/HttpClientContext', () => ({
  useHttpClientContext: () => ({ realtimeIsReady: state.ready }),
}));

vi.mock('react-admin', () => ({
  useDataProvider: () => ({
    subscribe: (topic: string, callback: (event: CrudEvent) => void) => {
      bus.subscribe(topic, callback);
      const set = bus.subs.get(topic) ?? new Set();
      set.add(callback);
      bus.subs.set(topic, set);
      return Promise.resolve({ data: null });
    },
    unsubscribe: (topic: string, callback: (event: CrudEvent) => void) => {
      bus.unsubscribe(topic, callback);
      bus.subs.get(topic)?.delete(callback);
      return Promise.resolve({ data: null });
    },
  }),
  useGetList: () => ({ data: state.listData, refetch: state.refetch }),
  useNotify: () => state.notify,
  useTranslate: () => (key: string) => key,
}));

const emit = (topic: string, event: CrudEvent) =>
  act(() => {
    bus.subs.get(topic)?.forEach((callback) => callback(event));
  });

const flush = (store: ReturnType<typeof createBackgroundJobStore>) =>
  act(() => {
    store.flushNow();
  });

const topicSize = (topic: string) => bus.subs.get(topic)?.size ?? 0;

beforeEach(() => {
  bus.subs.clear();
  bus.subscribe.mockClear();
  bus.unsubscribe.mockClear();
  state.listData = [];
  state.refetch.mockClear();
  state.notify.mockClear();
  state.ready = 1;
  vi.useFakeTimers();
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('BackgroundJobBridge', () => {
  it('watches the resource topic and seeds the running processes from the recovery fetch', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 0 });
    state.listData = [
      { id: 100, status: 'running', progress: 40 },
      { id: 101, status: 'running', progress: 10 },
    ];
    render(<BackgroundJobBridge store={store} />);
    flush(store);
    // the resource wide topic is subscribed once
    expect(topicSize(RESOURCE_TOPIC)).toBe(1);
    // both running processes recovered from the fetch are watched and stored
    expect(topicSize(processTopic(100))).toBe(1);
    expect(topicSize(processTopic(101))).toBe(1);
    expect(store.getSummary().running).toBe(2);
  });

  it('subscribes a newly running process and drops its topic when it finishes', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 0 });
    render(<BackgroundJobBridge store={store} />);
    flush(store);
    expect(topicSize(processTopic(7))).toBe(0);

    emit(RESOURCE_TOPIC, {
      type: 'created',
      payload: { ids: [7], records: [{ id: 7, status: 'running', progress: 0 } as RaRecord] },
    });
    flush(store);
    expect(topicSize(processTopic(7))).toBe(1);

    emit(processTopic(7), {
      type: 'updated',
      payload: { ids: [7], records: [{ id: 7, status: 'completed', progress: 100 } as RaRecord] },
    });
    flush(store);
    expect(store.getSummary().completed).toBe(1);
    // the finished process is no longer watched
    expect(topicSize(processTopic(7))).toBe(0);
  });

  it('applies a progress update and ignores a duplicate', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 0 });
    state.listData = [{ id: 5, status: 'running', progress: 20 }];
    render(<BackgroundJobBridge store={store} />);
    flush(store);
    emit(processTopic(5), {
      type: 'updated',
      payload: { ids: [5], records: [{ id: 5, status: 'running', progress: 60 } as RaRecord] },
    });
    flush(store);
    expect(store.getJobs().find((j) => j.id === 5)?.progress).toBe(60);
    // a stale lower update is dropped
    emit(processTopic(5), {
      type: 'updated',
      payload: { ids: [5], records: [{ id: 5, status: 'running', progress: 33 } as RaRecord] },
    });
    flush(store);
    expect(store.getJobs().find((j) => j.id === 5)?.progress).toBe(60);
  });

  it('removes a job when the bus reports it deleted', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 0 });
    state.listData = [{ id: 9, status: 'running', progress: 5 }];
    render(<BackgroundJobBridge store={store} />);
    flush(store);
    expect(store.getSummary().total).toBe(1);
    emit(RESOURCE_TOPIC, { type: 'delete', payload: { ids: [9] } });
    flush(store);
    expect(store.getSummary().total).toBe(0);
  });

  it('raises one aggregated error notification for a burst of failures', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 1000 });
    render(<BackgroundJobBridge store={store} />);
    flush(store);
    const failed = [11, 12, 13].map((id) => ({ id, status: 'failed' } as RaRecord));
    emit(RESOURCE_TOPIC, {
      type: 'created',
      payload: { ids: [11, 12, 13], records: failed },
    });
    // completions and running jobs never notify; a batch of failures does, once
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith(
      'backgroundJobs.notification.failedMany',
      expect.objectContaining({ type: 'error', messageArgs: expect.objectContaining({ smart_count: 3 }) }),
    );
  });

  it('does not notify for completions', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 1000 });
    render(<BackgroundJobBridge store={store} />);
    flush(store);
    emit(RESOURCE_TOPIC, {
      type: 'created',
      payload: { ids: [21], records: [{ id: 21, status: 'completed', progress: 100 } as RaRecord] },
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(state.notify).not.toHaveBeenCalled();
  });

  it('refetches only when the realtime bus reconnects after a drop', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 0 });
    state.ready = 0; // CONNECTING at mount
    const { rerender } = render(<BackgroundJobBridge store={store} />);
    flush(store);
    // first open is answered by the mount fetch, not a refetch
    state.ready = 1;
    rerender(<BackgroundJobBridge store={store} />);
    expect(state.refetch).not.toHaveBeenCalled();
    // the bus drops ...
    state.ready = 3; // CLOSED
    rerender(<BackgroundJobBridge store={store} />);
    // ... and comes back: the missed transitions are reconciled with a refetch
    state.ready = 1;
    rerender(<BackgroundJobBridge store={store} />);
    expect(state.refetch).toHaveBeenCalledTimes(1);
  });

  it('unwatches every topic when the bridge unmounts', () => {
    const store = createBackgroundJobStore({ throttleMs: 10, notifyMs: 0 });
    state.listData = [{ id: 1, status: 'running', progress: 1 }];
    const { unmount } = render(<BackgroundJobBridge store={store} />);
    flush(store);
    expect(topicSize(processTopic(1))).toBe(1);
    unmount();
    expect(topicSize(RESOURCE_TOPIC)).toBe(0);
    expect(topicSize(processTopic(1))).toBe(0);
  });
});
