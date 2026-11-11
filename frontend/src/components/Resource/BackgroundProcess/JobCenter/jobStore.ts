import { type RaRecord } from "react-admin";

/**
 * The state store of the Background Job Center (#1205).
 *
 * One entry per background process, keyed by the stable id which the api
 * answers. Events of the realtime bus and pages of the list endpoint are
 * both fed through `applyRecords`; neither can corrupt the state:
 *
 * - a record which arrives twice is written twice - the second write answers
 *   the same state and produces no transition, so nothing is announced twice;
 * - events may arrive out of order and without a sequence number, so a
 *   terminal process never moves back: the first terminal state which was
 *   seen is the state the center keeps.
 *
 * The store is bounded: at most `MAX_TRACKED_JOBS` records are held, and the
 * oldest terminal ones are dropped first. Aggregate counts are never read
 * from this store - they come from the collection endpoint - so a burst of
 * thousands of jobs cannot flood the drawer, the notifications or the memory
 * while the counts stay accurate.
 */

/** the logical states of a job as the backend contract answers them (#1207) */
export type JobState =
  | "queued"
  | "running"
  | "retrying"
  | "failed"
  | "completed"
  | "aborted";

export const JOB_STATES: readonly JobState[] = [
  "queued",
  "running",
  "retrying",
  "failed",
  "completed",
  "aborted",
];

/** the states which still move, the states which decide and the two groups
 *  the tabs of the drawer ask for */
export const ACTIVE_STATES: readonly JobState[] = [
  "queued",
  "running",
  "retrying",
];
export const TERMINAL_STATES: readonly JobState[] = [
  "failed",
  "completed",
  "aborted",
];
export const WAITING_STATES: readonly JobState[] = ["queued"];
export const FAILED_STATES: readonly JobState[] = ["failed", "aborted"];

/** the state contract's words mapped onto the status names of an api which
 *  does not answer `state` yet - an older deployment's payload stays readable */
const STATE_BY_STATUS: Record<string, JobState> = {
  pending: "queued",
  running: "running",
  completed: "completed",
  failed: "failed",
  aborted: "aborted",
};

/** a process as the Background Job Center reads it from the api */
export interface BackgroundJobRecord extends RaRecord {
  status: string;
  state?: string;
  processType: string;
  description?: string;
  phase?: string;
  progress?: number | null;
  totalSteps?: number | null;
  doneSteps?: number | null;
  dateCreated?: string;
  doneAt?: string | null;
  errorSummary?: string | null;
  isRetrying?: boolean;
  relatedResource?: { type: string; id: string } | null;
}

export const isJobState = (value: unknown): value is JobState =>
  typeof value === "string" &&
  (JOB_STATES as readonly string[]).includes(value);

/** the logical state of a record: the normalized state of the contract when
 *  the api answers it, the stored status - decorated with the retry flag the
 *  client cannot decide from the progress - as the fallback */
export const jobStateOf = (record: BackgroundJobRecord): JobState => {
  if (isJobState(record.state)) {
    return record.state;
  }
  const byStatus = STATE_BY_STATUS[record.status] ?? "running";
  if (byStatus === "running" && record.isRetrying === true) {
    return "retrying";
  }
  return byStatus;
};

export const isActive = (record: BackgroundJobRecord): boolean =>
  ACTIVE_STATES.includes(jobStateOf(record));

export const isTerminal = (record: BackgroundJobRecord): boolean =>
  TERMINAL_STATES.includes(jobStateOf(record));

/** the id of a process as the store keys it: the api answers integers, the
 *  websocket answers strings, so the store speaks strings everywhere */
export const jobId = (record: RaRecord): string => String(record.id);

/** the grouping key of a process: the resource its work happens on, or its
 *  process type when it names no resource */
export const jobGroupKey = (record: BackgroundJobRecord): string =>
  record.relatedResource
    ? `${record.relatedResource.type}/${record.relatedResource.id}`
    : record.processType;

/** how many processes the store holds at most */
export const MAX_TRACKED_JOBS = 300;

/** the transitions which the application of a batch produced - the only
 *  events the notification bridge is allowed to announce */
export interface JobTransitions {
  /** processes which moved into `failed` now - individually actionable */
  failed: BackgroundJobRecord[];
  /** processes which moved into `completed` now - announced aggregated */
  completed: BackgroundJobRecord[];
}

export interface JobStoreState {
  /** the tracked processes by id */
  jobs: Record<string, BackgroundJobRecord>;
}

export const initialJobStoreState = (): JobStoreState => ({ jobs: {} });

/**
 * Folds records into the state and reports the transitions it produced.
 *
 * A terminal process never moves back; an update of a process which is not
 * held yet is ignored - a process which left the store was deliberately
 * dropped, and it is the api's page which brings it back.
 */
export const applyRecords = (
  state: JobStoreState,
  records: BackgroundJobRecord[],
): { state: JobStoreState; transitions: JobTransitions } => {
  const jobs = { ...state.jobs };
  const transitions: JobTransitions = { failed: [], completed: [] };

  records.forEach((record) => {
    if (record === undefined || record.id === undefined || record.id === null) {
      return;
    }
    const id = jobId(record);
    const previous = jobs[id];
    if (previous !== undefined && isTerminal(previous)) {
      // out of order or duplicated: the first terminal state stands
      return;
    }
    jobs[id] = record;
    const stateOf = jobStateOf(record);
    const previousState =
      previous === undefined ? undefined : jobStateOf(previous);
    if (stateOf === "failed" && previousState !== "failed") {
      transitions.failed.push(record);
    } else if (stateOf === "completed" && previousState !== "completed") {
      transitions.completed.push(record);
    }
  });

  return { state: trim({ jobs }), transitions };
};

/** removes one process - the answer to a delete event of the bus */
export const removeJob = (state: JobStoreState, id: string): JobStoreState => {
  if (state.jobs[id] === undefined) {
    return state;
  }
  const jobs = { ...state.jobs };
  delete jobs[id];
  return { jobs };
};

/** keeps at most MAX_TRACKED_JOBS processes: active ones are held as far as
 *  they fit, terminal ones give their place from the oldest on */
export const trim = (state: JobStoreState): JobStoreState => {
  const records = Object.values(state.jobs);
  if (records.length <= MAX_TRACKED_JOBS) {
    return state;
  }
  const byNewest = (a: BackgroundJobRecord, b: BackgroundJobRecord) =>
    String(b.dateCreated ?? "").localeCompare(String(a.dateCreated ?? ""));
  const active = records
    .filter(isActive)
    .sort(byNewest)
    .slice(0, MAX_TRACKED_JOBS);
  const room = MAX_TRACKED_JOBS - active.length;
  const activeIds = new Set(active.map(jobId));
  const terminal = records
    .filter((record) => !activeIds.has(jobId(record)))
    .sort(byNewest)
    .slice(0, room);
  const jobs: Record<string, BackgroundJobRecord> = {};
  [...active, ...terminal].forEach((record) => {
    jobs[jobId(record)] = record;
  });
  return { jobs };
};

/** the tabs of the drawer and the states they show; "history" is answered by
 *  the api and not by this store */
export type JobTab = "all" | "running" | "waiting" | "failed";

const TAB_STATES: Record<JobTab, readonly JobState[]> = {
  all: JOB_STATES,
  running: ["running", "retrying"],
  waiting: WAITING_STATES,
  failed: FAILED_STATES,
};

/** the processes of one tab, newest first, narrowed by the search over the
 *  wording the row renders - the store is bounded, so the search runs over
 *  it in full; the complete history is searched on its list screen */
export const visibleJobs = (
  state: JobStoreState,
  tab: JobTab,
  search: string,
): BackgroundJobRecord[] => {
  const needle = search.trim().toLowerCase();
  const states: readonly string[] =
    tab === "failed" ? TAB_STATES.failed : TAB_STATES[tab];
  return Object.values(state.jobs)
    .filter((record) => (states as readonly string[]).includes(jobStateOf(record)))
    .filter(
      (record) =>
        needle === "" ||
        `${record.description ?? ""} ${record.processType} ${record.phase ?? ""}`
          .toLowerCase()
          .includes(needle),
    )
    .sort((a, b) =>
      String(b.dateCreated ?? "").localeCompare(String(a.dateCreated ?? "")),
    );
};

export interface JobGroup {
  key: string;
  records: BackgroundJobRecord[];
}

/**
 * Groups processes for the drawer: processes of one related resource share a
 * collapsible group, processes without one share the group of their type.
 * Groups are ordered by their most recent process.
 */
export const groupJobs = (records: BackgroundJobRecord[]): JobGroup[] => {
  const groups = new Map<string, BackgroundJobRecord[]>();
  records.forEach((record) => {
    const key = jobGroupKey(record);
    const group = groups.get(key);
    if (group === undefined) {
      groups.set(key, [record]);
    } else {
      group.push(record);
    }
  });
  return [...groups.entries()]
    .map(([key, group]) => ({ key, records: group }))
    .sort((a, b) =>
      String(
        b.records[0]?.dateCreated ?? "",
      ).localeCompare(String(a.records[0]?.dateCreated ?? "")),
    );
};

/** clears the completed processes from the view - the rows on the server are
 *  untouched, they remain in the history */
export const clearCompleted = (state: JobStoreState): JobStoreState => {
  const jobs: Record<string, BackgroundJobRecord> = {};
  Object.entries(state.jobs).forEach(([id, record]) => {
    if (jobStateOf(record) !== "completed") {
      jobs[id] = record;
    }
  });
  return { jobs };
};

/** whether a progress bar may answer a share: a process which does not know
 *  its total is indeterminate, and no percentage may be invented for it */
export const hasProgressTotal = (record: BackgroundJobRecord): boolean =>
  typeof record.totalSteps === "number" && record.totalSteps > 0;
