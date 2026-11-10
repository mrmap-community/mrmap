import type { Identifier, RaRecord } from 'react-admin';

/**
 * Central client-side state of the background operations the realtime bus pushes.
 *
 * The backend pushes every change of a BackgroundProcess over the realtime bus:
 * the create on the resource wide topic `resource/BackgroundProcess`, every
 * progress update on the record topic `resource/BackgroundProcess/<id>` (see
 * `notify/utils.py build_action_payload`). One message per task per step means
 * a high volume - hundreds of concurrent processes each write on every step.
 * Forwarding every one of them to the UI (the former `SnackbarObserver` enqueued
 * one snackbar per event) is exactly the flooding the Background Job Center
 * (#1203) removes.
 *
 * This store is the single aggregation point #1205 asks for:
 * - keyed by the stable operation id (the BackgroundProcess id);
 * - events are deduplicated, and out-of-order pushes never roll a job back;
 * - progress updates are coalesced, so a burst re-renders once, not per event;
 * - completions are aggregated into counts, they never notify on their own;
 * - only a job which *becomes* actionable (failed) feeds the notification
 *   bridge, and it does so once - aggregated, so a burst of failures is one
 *   notification and not one per task;
 * - bounded: finished jobs are evicted past `maxEntries`, running ones never.
 *
 * Like `providers/systemTimeProvider.ts` this is deliberately framework-free: a
 * module singleton fed imperatively, read through `useSyncExternalStore` (see
 * `useBackgroundJobs`). That keeps the aggregation independent of React and
 * unit-testable without a rendered tree.
 */

/** the five statuses the notify ProcessStatusEnum answers through get_status_display */
export const PENDING = 'pending';
export const RUNNING = 'running';
export const COMPLETED = 'completed';
export const FAILED = 'failed';
export const ABORTED = 'aborted';

export const TERMINAL_STATUSES: readonly string[] = [COMPLETED, FAILED, ABORTED];
export const ACTIVE_STATUSES: readonly string[] = [PENDING, RUNNING];

/**
 * the statuses which need the user to act. Today a failure is the only one;
 * #1207 normalises the states and may add review-required ones here.
 */
export const ACTIONABLE_STATUSES: readonly string[] = [FAILED];

export const isTerminalStatus = (status: string | undefined): boolean =>
  status !== undefined && TERMINAL_STATUSES.includes(status);

export const isActiveStatus = (status: string | undefined): boolean =>
  status !== undefined && ACTIVE_STATUSES.includes(status);

export const isActionableStatus = (status: string | undefined): boolean =>
  status !== undefined && ACTIONABLE_STATUSES.includes(status);

/** the order a job may move through; a lower rank never replaces a higher one */
export const statusRank = (status: string | undefined): number => {
  if (status === PENDING) return 0;
  if (isTerminalStatus(status)) return 2;
  return 1;
};

/** the fields a BackgroundProcess message carries; the store keeps only these. */
export interface BackgroundJobInput {
  id: Identifier;
  status?: string;
  processType?: string;
  description?: string;
  phase?: string;
  progress?: number | null;
  totalSteps?: number | null;
  doneSteps?: number | null;
  relatedResource?: { type: string; id: string } | null;
  dateCreated?: string;
  doneAt?: string;
}

/** a job as the store holds it: the input plus the derived aggregation flags. */
export interface BackgroundJob extends BackgroundJobInput {
  id: Identifier;
  actionable: boolean;
  /** a notification was already raised for this job's current failure */
  notified: boolean;
  /** wall-clock of the last accepted change, for the eviction order */
  updatedAt: number;
}

/** the counts #1206's AppBar indicator and drawer header read. */
export interface BackgroundJobSummary {
  total: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
  aborted: number;
  /** queued + running */
  active: number;
  /** completed + failed + aborted - the aggregated completions */
  finished: number;
  /** the jobs needing the user's attention */
  actionable: number;
  /** the mean progress of the active jobs, null while any total is unknown */
  aggregateProgress: number | null;
}

/** what a notification listener is handed when a flush drains the failures. */
export interface ActionableNotification {
  count: number;
  jobs: BackgroundJob[];
}

export interface BackgroundJobStoreOptions {
  /** the shortest interval between two publishes, in ms; 0 coalesces per burst */
  throttleMs?: number;
  /** the shortest interval between two notification flushes, in ms */
  notifyMs?: number;
  /** how many finished jobs to retain past the active ones; running jobs and
   * failures are never evicted - a failure is the discoverable signal, and the
   * long-term history store which prunes it is #1208 */
  maxEntries?: number;
  /** injectable clock, so the specs do not depend on the wall clock */
  now?: () => number;
}

const clampProgress = (value: number | null | undefined): number | undefined => {
  if (typeof value !== 'number' || Number.isNaN(value)) return undefined;
  return Math.min(100, Math.max(0, value));
};

const positiveNumber = (value: number | null | undefined): number | undefined =>
  typeof value === 'number' && !Number.isNaN(value) && value > 0 ? value : undefined;

const wholeNumber = (value: number | null | undefined): number | undefined =>
  typeof value === 'number' && !Number.isNaN(value) ? value : undefined;

/** the fields whose change makes an event worth keeping; equal means a duplicate. */
const sameContent = (stored: BackgroundJob, input: BackgroundJobInput): boolean =>
  stored.status === input.status &&
  stored.progress === clampProgress(input.progress) &&
  stored.doneSteps === wholeNumber(input.doneSteps) &&
  stored.totalSteps === positiveNumber(input.totalSteps) &&
  stored.phase === input.phase &&
  stored.description === input.description &&
  stored.processType === input.processType;

/**
 * whether an incoming input is older than what is already stored, so accepting
 * it would roll the job back. Two rules make the bus's delivery order irrelevant:
 * a finished job is never revived, and within an active status progress never
 * moves backwards.
 */
export const isOutdated = (stored: BackgroundJob, input: BackgroundJobInput): boolean => {
  if (isTerminalStatus(stored.status)) {
    // once finished, only another finished state may replace it
    return !isTerminalStatus(input.status);
  }
  // still active: never fall back to an earlier rank ...
  if (statusRank(input.status) < statusRank(stored.status)) return true;
  // ... and within the same active status, progress never regresses
  if (stored.status === input.status) {
    const incoming = clampProgress(input.progress);
    if (
      typeof stored.progress === 'number' &&
      typeof incoming === 'number' &&
      incoming < stored.progress
    ) {
      return true;
    }
  }
  return false;
};

const emptySummary = (): BackgroundJobSummary => ({
  total: 0,
  pending: 0,
  running: 0,
  completed: 0,
  failed: 0,
  aborted: 0,
  active: 0,
  finished: 0,
  actionable: 0,
  aggregateProgress: null,
});

/**
 * the mean progress over the active jobs, or null when no active job is
 * meaningful: none running, one without progress data, or none known.
 */
const computeAggregate = (
  active: number,
  progressUnknown: boolean,
  progressKnown: number,
  progressSum: number,
): number | null => {
  if (active === 0 || progressUnknown || progressKnown === 0) return null;
  return progressSum / progressKnown;
};

const summarize = (jobs: Iterable<BackgroundJob>): BackgroundJobSummary => {
  const summary = emptySummary();
  let progressSum = 0;
  let progressKnown = 0;
  let progressUnknown = false;
  for (const job of jobs) {
    summary.total += 1;
    switch (job.status) {
      case PENDING:
        summary.pending += 1;
        break;
      case RUNNING:
        summary.running += 1;
        break;
      case COMPLETED:
        summary.completed += 1;
        break;
      case FAILED:
        summary.failed += 1;
        break;
      case ABORTED:
        summary.aborted += 1;
        break;
      default:
        break;
    }
    if (isActiveStatus(job.status)) {
      summary.active += 1;
      if (typeof job.progress === 'number') {
        progressSum += job.progress;
        progressKnown += 1;
      } else {
        progressUnknown = true;
      }
    } else {
      summary.finished += 1;
    }
    if (job.actionable) summary.actionable += 1;
  }
  summary.aggregateProgress = computeAggregate(
    summary.active,
    progressUnknown,
    progressKnown,
    progressSum,
  );
  return summary;
};

/**
 * a store of background jobs. `apply` takes a live event, `seed` a recovery
 * snapshot; both run the same merge and out-of-order guard. See the file
 * header for the aggregation guarantees.
 */
export const createBackgroundJobStore = (options: BackgroundJobStoreOptions = {}) => {
  const throttleMs = options.throttleMs ?? 200;
  const notifyMs = options.notifyMs ?? 1000;
  const maxEntries = options.maxEntries ?? 200;
  const now = options.now ?? Date.now;

  const jobs = new Map<string, BackgroundJob>();
  const listeners = new Set<() => void>();
  const actionableListeners = new Set<(notification: ActionableNotification) => void>();

  // the failures accumulated since the last notification flush, deduplicated by id
  const pendingActionable = new Set<string>();

  // published snapshots: identical references until a flush, so
  // useSyncExternalStore re-renders only on a real change
  let jobsSnapshot: BackgroundJob[] = [];
  let summarySnapshot: BackgroundJobSummary = emptySummary();

  let renderTimer: ReturnType<typeof setTimeout> | undefined;
  let notifyTimer: ReturnType<typeof setTimeout> | undefined;

  const keyOf = String;

  const schedule = (
    current: ReturnType<typeof setTimeout> | undefined,
    ms: number,
    run: () => void,
  ): ReturnType<typeof setTimeout> | undefined => {
    if (current !== undefined) return current;
    return setTimeout(run, ms);
  };

  const publish = (): void => {
    jobsSnapshot = Array.from(jobs.values());
    summarySnapshot = summarize(jobs.values());
    listeners.forEach((listener) => listener());
  };

  const flushRender = (): void => {
    renderTimer = undefined;
    publish();
  };

  const flushNotify = (): void => {
    notifyTimer = undefined;
    if (pendingActionable.size === 0) return;
    const notified: BackgroundJob[] = [];
    pendingActionable.forEach((key) => {
      const job = jobs.get(key);
      if (job?.actionable) notified.push(job);
    });
    pendingActionable.clear();
    if (notified.length === 0) return;
    const notification: ActionableNotification = { count: notified.length, jobs: notified };
    actionableListeners.forEach((listener) => listener(notification));
  };

  const scheduleRender = (): void => {
    renderTimer = schedule(renderTimer, throttleMs, flushRender);
  };

  const scheduleNotify = (): void => {
    notifyTimer = schedule(notifyTimer, notifyMs, flushNotify);
  };

  const evict = (): void => {
    // bound the retained finished jobs; active jobs and failures stay, so the
    // store's memory is bounded by maxEntries finished jobs plus the live work
    if (jobs.size <= maxEntries) return;
    const evictable = Array.from(jobs.values())
      .filter(
        (job) =>
          isTerminalStatus(job.status) &&
          !job.actionable &&
          !pendingActionable.has(keyOf(job.id)),
      )
      .sort((a, b) => a.updatedAt - b.updatedAt);
    for (const job of evictable) {
      if (jobs.size <= maxEntries) break;
      jobs.delete(keyOf(job.id));
    }
  };

  /**
   * merge one input into the store.
   * @param origin 'live' for a realtime event, 'seed' for a recovery snapshot:
   * a job seen for the first time through a seed is history already known, so
   * it must not notify; a job seen for the first time through a live event that
   * already failed is a fresh failure and does.
   */
  const apply = (
    input: BackgroundJobInput,
    origin: 'live' | 'seed' = 'live',
  ): 'applied' | 'duplicate' | 'outdated' => {
    if (input?.id === undefined || input?.id === null) {
      return 'outdated';
    }
    const key = keyOf(input.id);
    const stored = jobs.get(key);

    if (stored && (isOutdated(stored, input) || sameContent(stored, input))) {
      return isOutdated(stored, input) ? 'outdated' : 'duplicate';
    }

    const status = input.status;
    const wasActionable = stored?.actionable ?? (origin === 'seed' && isActionableStatus(status));
    const actionable = isActionableStatus(status);

    const job: BackgroundJob = {
      id: input.id,
      status,
      processType: input.processType,
      description: input.description,
      phase: input.phase,
      progress: clampProgress(input.progress),
      totalSteps: positiveNumber(input.totalSteps),
      doneSteps: wholeNumber(input.doneSteps),
      relatedResource: input.relatedResource ?? undefined,
      dateCreated: input.dateCreated,
      doneAt: input.doneAt,
      actionable,
      // a first-seen job through a seed is history: mark it already told
      notified: stored?.notified ?? (origin === 'seed' && actionable),
      updatedAt: now(),
    };
    jobs.set(key, job);

    // a job which *becomes* actionable joins the aggregated notification; a job
    // which leaves the failed state can notify again on a later failure
    if (actionable && !wasActionable && !job.notified) {
      pendingActionable.add(key);
      job.notified = true;
      scheduleNotify();
    } else if (!actionable) {
      job.notified = false;
    }

    evict();
    scheduleRender();
    return 'applied';
  };

  /** feed a whole snapshot (a reload or a reconnect recovery) without notifying history. */
  const seed = (inputs: BackgroundJobInput[]): void => {
    inputs.forEach((input) => apply(input, 'seed'));
  };

  /** drop a job when the bus reports it deleted. */
  const remove = (id: Identifier): void => {
    const key = keyOf(id);
    if (jobs.delete(key)) {
      pendingActionable.delete(key);
      scheduleRender();
    }
  };

  /** publish immediately, skipping the throttle - used to seed the first paint. */
  const flushNow = (): void => {
    if (renderTimer !== undefined) {
      clearTimeout(renderTimer);
      renderTimer = undefined;
    }
    publish();
  };

  const subscribe = (listener: () => void): (() => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  };

  const subscribeActionable = (
    listener: (notification: ActionableNotification) => void,
  ): (() => void) => {
    actionableListeners.add(listener);
    return () => {
      actionableListeners.delete(listener);
    };
  };

  const getJobs = (): BackgroundJob[] => jobsSnapshot;
  const getSummary = (): BackgroundJobSummary => summarySnapshot;

  /** the ids the bridge must watch: the jobs which are not finished yet. */
  const getActiveKeys = (): string[] =>
    Array.from(jobs.values())
      .filter((job) => isActiveStatus(job.status))
      .map((job) => keyOf(job.id))
      .sort((a, b) => a.localeCompare(b));

  /** release every timer and listener - used by the specs and hot reload. */
  const destroy = (): void => {
    if (renderTimer !== undefined) clearTimeout(renderTimer);
    if (notifyTimer !== undefined) clearTimeout(notifyTimer);
    renderTimer = undefined;
    notifyTimer = undefined;
    listeners.clear();
    actionableListeners.clear();
    jobs.clear();
    pendingActionable.clear();
    jobsSnapshot = [];
    summarySnapshot = emptySummary();
  };

  return {
    apply,
    seed,
    remove,
    flushNow,
    subscribe,
    subscribeActionable,
    getJobs,
    getSummary,
    getActiveKeys,
    destroy,
  };
};

export type BackgroundJobStore = ReturnType<typeof createBackgroundJobStore>;

/** read the fields the store keeps off a BackgroundProcess record or message. */
export const toJobInput = (record: RaRecord): BackgroundJobInput | undefined => {
  if (record?.id === undefined) return undefined;
  return {
    id: record.id,
    status: typeof record.status === 'string' ? record.status : undefined,
    processType: typeof record.processType === 'string' ? record.processType : undefined,
    description: typeof record.description === 'string' ? record.description : undefined,
    phase: typeof record.phase === 'string' ? record.phase : undefined,
    progress: typeof record.progress === 'number' ? record.progress : null,
    totalSteps: typeof record.totalSteps === 'number' ? record.totalSteps : null,
    doneSteps: typeof record.doneSteps === 'number' ? record.doneSteps : null,
    relatedResource:
      record.relatedResource && typeof record.relatedResource === 'object'
        ? (record.relatedResource as { type: string; id: string })
        : null,
    dateCreated: typeof record.dateCreated === 'string' ? record.dateCreated : undefined,
    doneAt: typeof record.doneAt === 'string' ? record.doneAt : undefined,
  };
};

/**
 * the application-wide store. The bridge feeds it, the screens read it. Kept as
 * a module singleton so it survives route changes and the components which show
 * the jobs do not own it.
 */
export const backgroundJobStore = createBackgroundJobStore();

export default backgroundJobStore;
