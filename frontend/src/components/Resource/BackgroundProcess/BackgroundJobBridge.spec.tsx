import type { BackgroundJobRecord } from './JobCenter/jobStore';

import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BackgroundJobBridge from './BackgroundJobBridge';

// the center's failure seam (#1461): the spec drives it directly - what the
// store reports as a live failure is exactly the bridge's input
const state = vi.hoisted(() => ({
  listeners: new Set<(records: BackgroundJobRecord[]) => void>(),
  subscribeFailed: vi.fn(),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  notify: vi.fn(),
}));

vi.mock('react-admin', () => ({
  useNotify: () => state.notify,
  useTranslate: () => (key: string) => key,
  // the bus belongs to the center: a bridge which still reached for the
  // dataProvider would trip the spy below
  useDataProvider: () => ({ subscribe: state.subscribe, unsubscribe: state.unsubscribe }),
}));

vi.mock('./JobCenter/BackgroundJobCenterContext', () => ({
  useBackgroundJobCenter: () => ({
    subscribeFailed: (listener: (records: BackgroundJobRecord[]) => void) => {
      state.listeners.add(listener);
      state.subscribeFailed(listener);
      return () => {
        state.listeners.delete(listener);
      };
    },
  }),
}));

const failed = (...ids: number[]): BackgroundJobRecord[] =>
  ids.map((id) => ({ id, status: 'failed' }) as BackgroundJobRecord);

const tellFailures = (records: BackgroundJobRecord[]) =>
  act(() => {
    state.listeners.forEach((listener) => listener(records));
  });

beforeEach(() => {
  state.listeners.clear();
  state.subscribeFailed.mockClear();
  state.subscribe.mockClear();
  state.unsubscribe.mockClear();
  state.notify.mockClear();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('BackgroundJobBridge', () => {
  it('raises one aggregated error notification for a burst of failures', () => {
    render(<BackgroundJobBridge />);
    tellFailures(failed(11, 12, 13));
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith('backgroundJobs.notification.failedMany', {
      type: 'error',
    });
  });

  it('names a single failure with the one-failure wording', () => {
    render(<BackgroundJobBridge />);
    tellFailures(failed(21));
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith('backgroundJobs.notification.failedOne', {
      type: 'error',
    });
  });

  it('sums bursts which arrive within one aggregation window into one message', () => {
    render(<BackgroundJobBridge />);
    tellFailures(failed(31));
    act(() => {
      vi.advanceTimersByTime(400);
    });
    tellFailures(failed(32, 33));
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith('backgroundJobs.notification.failedMany', {
      type: 'error',
    });
  });

  it('opens the window again for a burst which starts after the quiet moment', () => {
    render(<BackgroundJobBridge />);
    tellFailures(failed(41));
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    tellFailures(failed(42));
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(state.notify).toHaveBeenCalledTimes(2);
  });

  it('stays quiet while the center reports nothing', () => {
    render(<BackgroundJobBridge />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(state.notify).not.toHaveBeenCalled();
  });

  it('subscribes the failure seam once and no realtime topic', () => {
    render(<BackgroundJobBridge />);
    expect(state.subscribeFailed).toHaveBeenCalledTimes(1);
    // the convergence of #1461: the bridge owns no subscription of its own
    expect(state.subscribe).not.toHaveBeenCalled();
    expect(state.unsubscribe).not.toHaveBeenCalled();
  });

  it('unregisters on unmount and drops a burst which had not reached its moment', () => {
    const { unmount } = render(<BackgroundJobBridge />);
    tellFailures(failed(51));
    unmount();
    expect(state.listeners.size).toBe(0);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(state.notify).not.toHaveBeenCalled();
  });
});
