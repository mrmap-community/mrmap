import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createBackgroundJobStore,
  toJobInput,
  type BackgroundJob,
  type BackgroundJobInput,
} from './jobsStore';

// a deterministic clock so eviction order and updatedAt do not depend on the wall clock
let clock = 0;
const now = () => clock;
const tick = () => {
  clock += 1;
};

const job = (id: string | number, fields: Partial<BackgroundJobInput> = {}): BackgroundJobInput => ({
  id,
  status: 'running',
  progress: 0,
  ...fields,
});

const published = (
  store: ReturnType<typeof createBackgroundJobStore>,
): BackgroundJob[] => {
  store.flushNow();
  return store.getJobs();
};

beforeEach(() => {
  clock = 0;
  vi.useFakeTimers();
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('background job store - keying and deduplication', () => {
  it('keys jobs by their stable operation id', () => {
    const store = createBackgroundJobStore({ now });
    store.apply(job('a', { phase: 'one' }));
    store.apply(job('b', { phase: 'two' }));
    store.apply(job('a', { phase: 'three' }));
    const jobs = published(store);
    expect(jobs).toHaveLength(2);
    expect(jobs.find((j) => j.id === 'a')?.phase).toBe('three');
    expect(jobs.find((j) => j.id === 'b')?.phase).toBe('two');
  });

  it('treats an identical push as a duplicate and keeps the first record', () => {
    const store = createBackgroundJobStore({ now });
    expect(store.apply(job(1, { status: 'running', progress: 40, phase: 'x' }))).toBe('applied');
    tick();
    expect(store.apply(job(1, { status: 'running', progress: 40, phase: 'x' }))).toBe('duplicate');
    const [only] = published(store);
    expect(only.updatedAt).toBe(0);
  });
});

describe('background job store - out-of-order events', () => {
  it('never lets progress move backwards within a running job', () => {
    const store = createBackgroundJobStore({ now });
    store.apply(job(1, { status: 'running', progress: 80 }));
    expect(store.apply(job(1, { status: 'running', progress: 60 }))).toBe('outdated');
    expect(store.apply(job(1, { status: 'running', progress: 95 }))).toBe('applied');
    expect(published(store)[0].progress).toBe(95);
  });

  it('never revives a finished job with a late running update', () => {
    const store = createBackgroundJobStore({ now });
    store.apply(job(1, { status: 'completed', progress: 100 }));
    expect(store.apply(job(1, { status: 'running', progress: 40 }))).toBe('outdated');
    expect(published(store)[0].status).toBe('completed');
  });

  it('never falls back to an earlier status rank', () => {
    const store = createBackgroundJobStore({ now });
    store.apply(job(1, { status: 'running', progress: 10 }));
    expect(store.apply(job(1, { status: 'pending', progress: 0 }))).toBe('outdated');
    expect(published(store)[0].status).toBe('running');
  });

  it('applies events that arrive out of order to the latest state', () => {
    const store = createBackgroundJobStore({ now });
    // the terminal event arrives first, the older progress afterwards
    store.apply(job(1, { status: 'completed', progress: 100, doneSteps: 5, totalSteps: 5 }));
    store.apply(job(1, { status: 'running', progress: 20, doneSteps: 1, totalSteps: 5 }));
    store.apply(job(1, { status: 'running', progress: 60, doneSteps: 3, totalSteps: 5 }));
    const [only] = published(store);
    expect(only.status).toBe('completed');
    expect(only.progress).toBe(100);
  });
});

describe('background job store - high volume bursts are coalesced', () => {
  it('publishes a thousand events once, not once per event', () => {
    const store = createBackgroundJobStore({ throttleMs: 200, maxEntries: 5000, now });
    const renderListener = vi.fn();
    store.subscribe(renderListener);
    for (let id = 0; id < 1000; id += 1) {
      tick();
      store.apply(job(id, { status: 'running', progress: id % 100 }));
    }
    // nothing published yet: the flush is throttled to the end of the burst
    expect(renderListener).not.toHaveBeenCalled();
    vi.advanceTimersByTime(200);
    // exactly one coalesced publish carries the whole burst
    expect(renderListener).toHaveBeenCalledTimes(1);
    expect(store.getJobs()).toHaveLength(1000);
  });

  it('collapses a run of progress pushes into a single re-render', () => {
    const store = createBackgroundJobStore({ throttleMs: 100, now });
    const renderListener = vi.fn();
    store.subscribe(renderListener);
    for (let step = 1; step <= 50; step += 1) {
      tick();
      store.apply(job(1, { status: 'running', progress: step * 2 }));
      // each push may schedule, but the throttle coalesces them
      vi.advanceTimersByTime(0);
    }
    vi.advanceTimersByTime(100);
    expect(renderListener).toHaveBeenCalledTimes(1);
    expect(store.getSummary().aggregateProgress).toBe(100);
  });
});

describe('background job store - completion aggregation', () => {
  it('aggregates completions and active/finished counts without notifying', () => {
    const store = createBackgroundJobStore({ throttleMs: 0, notifyMs: 0, now });
    const actionable = vi.fn();
    store.subscribeActionable(actionable);
    store.apply(job(1, { status: 'completed', progress: 100 }));
    store.apply(job(2, { status: 'completed', progress: 100 }));
    store.apply(job(3, { status: 'running', progress: 50 }));
    store.apply(job(4, { status: 'pending', progress: 0 }));
    const summary = (() => {
      store.flushNow();
      return store.getSummary();
    })();
    expect(summary.completed).toBe(2);
    expect(summary.finished).toBe(2);
    expect(summary.active).toBe(2);
    expect(summary.running).toBe(1);
    expect(summary.pending).toBe(1);
    expect(summary.total).toBe(4);
    // completions never raise a notification on their own
    vi.advanceTimersByTime(10);
    expect(actionable).not.toHaveBeenCalled();
  });
});

describe('background job store - actionable notifications', () => {
  it('notifies once for a distinct failure and not for a duplicate', () => {
    const store = createBackgroundJobStore({ notifyMs: 1000, now });
    const actionable = vi.fn();
    store.subscribeActionable(actionable);
    store.apply(job(1, { status: 'failed' }));
    store.apply(job(1, { status: 'failed' })); // duplicate
    vi.advanceTimersByTime(1000);
    expect(actionable).toHaveBeenCalledTimes(1);
    expect(actionable).toHaveBeenCalledWith(expect.objectContaining({ count: 1 }));
  });

  it('aggregates a burst of distinct failures into one notification', () => {
    const store = createBackgroundJobStore({ notifyMs: 1000, now });
    const actionable = vi.fn();
    store.subscribeActionable(actionable);
    for (let id = 0; id < 200; id += 1) {
      tick();
      store.apply(job(id, { status: 'failed' }));
    }
    vi.advanceTimersByTime(1000);
    expect(actionable).toHaveBeenCalledTimes(1);
    expect(actionable).toHaveBeenCalledWith(expect.objectContaining({ count: 200 }));
  });

  it('does not notify for failures which were already known when seeded', () => {
    const store = createBackgroundJobStore({ notifyMs: 1000, now });
    const actionable = vi.fn();
    store.subscribeActionable(actionable);
    // a reload recovers already-failed processes from history
    store.seed([job(1, { status: 'failed' }), job(2, { status: 'failed' })]);
    vi.advanceTimersByTime(1000);
    expect(actionable).not.toHaveBeenCalled();
    expect(store.getSummary().failed).toBe(2);
  });

  it('surfaces a failure missed during a drop when a recovery seed advances a running job', () => {
    const store = createBackgroundJobStore({ notifyMs: 1000, now });
    const actionable = vi.fn();
    store.subscribeActionable(actionable);
    store.apply(job(1, { status: 'running', progress: 30 })); // seen live
    vi.advanceTimersByTime(1000);
    expect(actionable).not.toHaveBeenCalled();
    // reconnect refetch reveals the job failed while the socket was down
    store.seed([job(1, { status: 'failed' })]);
    vi.advanceTimersByTime(1000);
    expect(actionable).toHaveBeenCalledTimes(1);
    expect(actionable).toHaveBeenCalledWith(expect.objectContaining({ count: 1 }));
  });

  it('notifies again when a job recovers and then fails a second time', () => {
    const store = createBackgroundJobStore({ notifyMs: 0, now });
    const actionable = vi.fn();
    store.subscribeActionable(actionable);
    store.apply(job(1, { status: 'failed' }));
    vi.advanceTimersByTime(0);
    store.apply(job(1, { status: 'completed', progress: 100 })); // leaves the failed state
    store.apply(job(1, { status: 'failed' })); // fails again
    vi.advanceTimersByTime(0);
    expect(actionable).toHaveBeenCalledTimes(2);
  });
});

describe('background job store - bounded memory', () => {
  it('evicts the oldest finished jobs but keeps the running ones', () => {
    const store = createBackgroundJobStore({ maxEntries: 3, now });
    store.apply(job('run', { status: 'running', progress: 10 }));
    tick();
    store.apply(job('f1', { status: 'completed', progress: 100 }));
    tick();
    store.apply(job('f2', { status: 'completed', progress: 100 }));
    tick();
    store.apply(job('f3', { status: 'completed', progress: 100 }));
    tick();
    store.apply(job('f4', { status: 'completed', progress: 100 }));
    const ids = published(store).map((j) => String(j.id)).sort();
    // keeps the running one and the newest finished ones, drops the two oldest
    expect(ids).toEqual(['run', 'f3', 'f4'].sort());
    expect(ids).not.toContain('f1');
    expect(ids).not.toContain('f2');
    expect(ids).toContain('run');
  });

  it('caps the tracked entries under a high volume of finished jobs', () => {
    const store = createBackgroundJobStore({ maxEntries: 50, now });
    for (let id = 0; id < 1000; id += 1) {
      tick();
      store.apply(job(id, { status: 'completed', progress: 100 }));
    }
    store.flushNow();
    expect(store.getJobs().length).toBeLessThanOrEqual(50);
  });
});

describe('toJobInput', () => {
  it('reads only the fields the store keeps and coerces the rest', () => {
    const input = toJobInput({
      id: 7,
      status: 'running',
      progress: 50,
      totalSteps: 6,
      doneSteps: 3,
      processType: 'harvesting',
      phase: 'Collecting',
      description: 'desc',
      relatedResource: { type: 'CatalogueService', id: 'abc' },
      url: 'http://ignored',
    });
    expect(input).toEqual({
      id: 7,
      status: 'running',
      processType: 'harvesting',
      description: 'desc',
      phase: 'Collecting',
      progress: 50,
      totalSteps: 6,
      doneSteps: 3,
      relatedResource: { type: 'CatalogueService', id: 'abc' },
      dateCreated: undefined,
      doneAt: undefined,
    });
  });

  it('returns undefined for a record without an id', () => {
    expect(
      toJobInput({ status: 'running' } as unknown as Parameters<typeof toJobInput>[0]),
    ).toBeUndefined();
  });
});
