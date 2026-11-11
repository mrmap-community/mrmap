import { useCallback, useSyncExternalStore } from 'react';

import {
  backgroundJobStore,
  type BackgroundJob,
  type BackgroundJobStore,
  type BackgroundJobSummary,
} from './jobsStore';

export interface UseBackgroundJobsResult {
  jobs: BackgroundJob[];
  summary: BackgroundJobSummary;
}

/**
 * read the aggregated background-job state. The store is a framework-free
 * singleton (see `jobsStore`); this hook only bridges it to React through
 * `useSyncExternalStore`, which re-renders on the store's coalesced publish -
 * a burst of progress events becomes a single re-render, not one per event.
 *
 * A caller may pass another store instance (the specs do); it defaults to the
 * application-wide one.
 */
export const useBackgroundJobs = (
  store: BackgroundJobStore = backgroundJobStore,
): UseBackgroundJobsResult => {
  const subscribe = useCallback((onStoreChange: () => void) => store.subscribe(onStoreChange), [store]);
  const getJobs = useCallback(() => store.getJobs(), [store]);
  const getSummary = useCallback(() => store.getSummary(), [store]);

  const jobs = useSyncExternalStore(subscribe, getJobs, getJobs);
  const summary = useSyncExternalStore(subscribe, getSummary, getSummary);

  return { jobs, summary };
};

export default useBackgroundJobs;
