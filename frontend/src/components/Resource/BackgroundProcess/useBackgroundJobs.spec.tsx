import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createBackgroundJobStore, type BackgroundJobInput } from './jobsStore';
import { useBackgroundJobs } from './useBackgroundJobs';

const job = (id: string | number, fields: Partial<BackgroundJobInput> = {}): BackgroundJobInput => ({
  id,
  status: 'running',
  progress: 0,
  ...fields,
});

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('useBackgroundJobs', () => {
  it('returns the published jobs and the aggregate summary', () => {
    const store = createBackgroundJobStore({ throttleMs: 200 });
    act(() => {
      store.apply(job(1, { status: 'running', progress: 20 }));
      store.apply(job(2, { status: 'completed', progress: 100 }));
      store.flushNow();
    });
    const { result } = renderHook(() => useBackgroundJobs(store));
    expect(result.current.jobs).toHaveLength(2);
    expect(result.current.summary.total).toBe(2);
    expect(result.current.summary.completed).toBe(1);
    expect(result.current.summary.running).toBe(1);
  });

  it('re-renders once when a coalesced burst is published', () => {
    const store = createBackgroundJobStore({ throttleMs: 200 });
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useBackgroundJobs(store);
    });
    const initialRenders = renders;
    act(() => {
      for (let id = 0; id < 500; id += 1) store.apply(job(id, { status: 'running', progress: 1 }));
    });
    // the burst is throttled: no re-render until the flush fires
    expect(renders).toBe(initialRenders);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(renders).toBe(initialRenders + 1);
    expect(result.current.summary.total).toBe(500);
  });

  it('does not re-render for a duplicate push', () => {
    const store = createBackgroundJobStore({ throttleMs: 50 });
    act(() => {
      store.apply(job(1, { status: 'running', progress: 30 }));
      store.flushNow();
    });
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useBackgroundJobs(store);
    });
    const baseline = renders;
    act(() => {
      store.apply(job(1, { status: 'running', progress: 30 })); // duplicate: no publish
      vi.advanceTimersByTime(50);
    });
    expect(renders).toBe(baseline);
    expect(result.current.summary.running).toBe(1);
  });
});
