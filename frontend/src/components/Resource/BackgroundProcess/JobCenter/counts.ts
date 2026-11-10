/**
 * The aggregate counts of the Background Job Center (#1206).
 *
 * The counters of the app bar, the tiles of the drawer and the numbers in
 * its tab labels are never read from the client-side store: a deployment may
 * have thousands of processes and the store is bounded, while the collection
 * endpoint always answers the accurate total. The filters below are shared by
 * every consumer so that the same query - and one `Count` fetch - answers
 * all of them at once.
 */

/** the states each counter counts, as the api's status filter names them */
export const JOB_COUNT_FILTERS = {
  running: { status: "running" },
  waiting: { status: "pending" },
  failed: { status: "failed,aborted" },
  completed: { status: "completed" },
} as const;

/** the sort which matches the default ordering of the endpoint; naming it
 *  explicitly keeps every consumer on the same query */
export const JOB_COUNT_SORT = { field: "dateCreated", order: "DESC" } as const;

/** the history window of the "completed" tile, in milliseconds */
export const COMPLETED_WINDOW_MILLISECONDS = 24 * 60 * 60 * 1000;

/** the tiles and counters read the totals of the collection; a poll is the
 *  floor under which the numbers converge even while the realtime bus keeps
 *  the rows themselves live (the counts are not pushed - see #1206) */
export const COUNTS_POLL_MILLISECONDS = 10000;

/**
 * The filter for the completions of the last day.
 *
 * The cutoff is computed once per mount of the consuming component: a value
 * which changed on every render would make every poll a new query.
 */
export const completedWithinDayFilter = (
  now: number = Date.now(),
): Record<string, string> => ({
  ...JOB_COUNT_FILTERS.completed,
  doneAt_filter_lookup_gt: new Date(
    now - COMPLETED_WINDOW_MILLISECONDS,
  ).toISOString(),
});
