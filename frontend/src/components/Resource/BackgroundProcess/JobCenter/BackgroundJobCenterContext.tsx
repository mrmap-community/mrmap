import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  useDataProvider,
  useGetList,
  useNotify,
  useTranslate,
} from "react-admin";
import { ReadyState } from "react-use-websocket";

import { useHttpClientContext } from "../../../../context/HttpClientContext";
import { type CrudEvent } from "../../../../providers/dataProvider";
import JobCenterDrawer from "./JobCenterDrawer";
import {
  applyRecords,
  clearCompleted as clearCompletedFrom,
  isActive,
  jobId,
  initialJobStoreState,
  removeJob,
  trim,
  type BackgroundJobRecord,
  type JobStoreState,
  MAX_TRACKED_JOBS,
} from "./jobStore";

/** the processes one hydrate page answers; the pages together cover the
 *  bounded store after a reload, newest first */
const HYDRATE_PAGE_SIZE = Math.ceil(MAX_TRACKED_JOBS / 2);

/** the newest active processes which get a per-id topic of their own; older
 *  active ones stay visible but only refresh with a page of the api */
const MAX_ID_TOPICS = 100;

/** the fallback distance between api reads while the realtime bus is down */
const FALLBACK_POLL_MILLISECONDS = 20000;

/** the quiet distance after which the completions which arrived in a burst
 *  are announced together - long enough that the answers of one bulk run
 *  collapse into one message, short enough to stay in front of the user */
const COMPLETION_QUIET_MILLISECONDS = 3000;

export interface BackgroundJobCenterContextValue {
  /** the bounded store of tracked processes */
  state: JobStoreState;
  /** whether the drawer is open */
  open: boolean;
  setOpen: (open: boolean) => void;
  /** drops the completed processes from the view; the server keeps them */
  clearCompleted: () => void;
}

const BackgroundJobCenterContext = createContext<
  BackgroundJobCenterContextValue | undefined
>(undefined);

export const useBackgroundJobCenter =
  (): BackgroundJobCenterContextValue => {
    const context = useContext(BackgroundJobCenterContext);
    if (context === undefined) {
      throw new Error(
        "useBackgroundJobCenter must be used inside a BackgroundJobCenterProvider",
      );
    }
    return context;
  };

/**
 * The single client-side state of the Background Job Center (#1205).
 *
 * Everything the drawer and the activity counter of the app bar show reads
 * from here:
 *
 * - the store is hydrated from the api on mount and on every reconnect of
 *   the realtime bus, so a page load or a lost connection cannot hide the
 *   work which is running or the failures which are waiting;
 * - the realtime bus feeds it: creates on the resource-wide topic, updates
 *   on the per-id topics of the active processes the store tracks (the
 *   backend delivers updates of a process only to subscribers of its own
 *   topic - see notify/consumers.py and RealtimeListBase);
 * - the notification bridge announces only what a user has to act on: a
 *   failure once per process, and completions not per task but aggregated
 *   after a quiet moment. No toast is ever made for a progress update.
 */
export const BackgroundJobCenterProvider = ({
  children,
  notifications = true,
}: {
  children: ReactNode;
  /** whether this provider speaks its transitions through `useNotify`; a
   *  deployment which mounts another notification bridge for the same
   *  processes (the `BackgroundJobBridge` of #1205 in the Layout) passes
   *  false, so one failure never becomes two toasts */
  notifications?: boolean;
}): ReactNode => {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const translate = useTranslate();
  const { realtimeIsReady } = useHttpClientContext();

  const [state, setState] = useState<JobStoreState>(initialJobStoreState);
  const [open, setOpen] = useState(false);

  // the completions which wait for their aggregated announcement
  const pendingCompletions = useRef(0);
  const completionTimer = useRef<
    ReturnType<typeof setTimeout> | undefined
  >(undefined);

  // the pages which rebuild the store on mount and after every reconnect:
  // the work which did not end yet, and the processes which decided recently
  // (the failures have to be discoverable after a reload, not only live)
  const activeProcesses = useGetList<BackgroundJobRecord>("BackgroundProcess", {
    filter: { status: "pending,running" },
    sort: { field: "dateCreated", order: "DESC" },
    pagination: { page: 1, perPage: HYDRATE_PAGE_SIZE },
  });
  const recentTerminal = useGetList<BackgroundJobRecord>("BackgroundProcess", {
    filter: { status: "failed,aborted,completed" },
    sort: { field: "dateCreated", order: "DESC" },
    pagination: { page: 1, perPage: HYDRATE_PAGE_SIZE },
  });

  // the store is mirrored in a ref so that the announcements of a batch are
  // made next to the state write and never inside a state updater, which
  // React may run twice
  const stateRef = useRef(state);
  const commit = useCallback((next: JobStoreState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  /** folds records into the store; only `announce` makes notifications - the
   *  bridge speaks for live events, never for a hydration replay */
  const ingest = useCallback(
    (records: BackgroundJobRecord[], announce: boolean) => {
      if (records.length === 0) return;
      const { state: next, transitions } = applyRecords(
        stateRef.current,
        records,
      );
      if (announce && notifications) {
        transitions.failed.forEach((record) => {
          // once per process: the terminal state is written once and the
          // store never lets a process move back, so the same failure is
          // never announced twice, no matter how often its message arrives
          notify("backgroundActivity.jobCenter.notifyFailed", {
            type: "warning",
            messageArgs: {
              description:
                record.description ||
                translate("backgroundActivity.process", {
                  id: String(record.id),
                }),
            },
          });
        });
        if (transitions.completed.length > 0) {
          pendingCompletions.current += transitions.completed.length;
          if (completionTimer.current !== undefined) {
            clearTimeout(completionTimer.current);
          }
          completionTimer.current = setTimeout(() => {
            const count = pendingCompletions.current;
            pendingCompletions.current = 0;
            completionTimer.current = undefined;
            notify("backgroundActivity.jobCenter.notifyCompleted", {
              type: "success",
              messageArgs: { count, smart_count: count },
            });
          }, COMPLETION_QUIET_MILLISECONDS);
        }
      }
      commit(next);
    },
    [commit, notify, translate, notifications],
  );

  // hydration: every fresh page of the two windows rebuilds the store
  useEffect(() => {
    ingest(activeProcesses.data ?? [], false);
  }, [activeProcesses.data, ingest]);
  useEffect(() => {
    ingest(recentTerminal.data ?? [], false);
  }, [recentTerminal.data, ingest]);

  // reconnect recovery: the state of processes which moved while the socket
  // was gone is answered by the api, not by the missed messages
  const wasOpen = useRef(false);
  useEffect(() => {
    const isUp = realtimeIsReady === ReadyState.OPEN;
    if (isUp && !wasOpen.current) {
      void activeProcesses.refetch();
      void recentTerminal.refetch();
    }
    wasOpen.current = isUp;
  }, [
    realtimeIsReady,
    activeProcesses.refetch,
    recentTerminal.refetch,
  ]);

  // fallback: while the bus is not up, the pages are read periodically
  useEffect(() => {
    if (realtimeIsReady === ReadyState.OPEN) {
      return;
    }
    const interval = setInterval(() => {
      void activeProcesses.refetch();
      void recentTerminal.refetch();
    }, FALLBACK_POLL_MILLISECONDS);
    return () => clearInterval(interval);
  }, [realtimeIsReady, activeProcesses.refetch, recentTerminal.refetch]);

  // the resource-wide topic: creates arrive with their record, deletes ask
  // for the row to disappear from the view
  useEffect(() => {
    const handleResourceEvent = (event: CrudEvent): void => {
      if (event.type === "created") {
        ingest((event.payload.records ?? []) as BackgroundJobRecord[], true);
        return;
      }
      if (event.type === "deleted" || event.type === "delete") {
        event.payload.ids.forEach((id) =>
          commit(removeJob(stateRef.current, String(id))),
        );
      }
    };
    void dataProvider.subscribe(
      "resource/BackgroundProcess",
      handleResourceEvent,
    );
    return () => {
      void dataProvider.unsubscribe(
        "resource/BackgroundProcess",
        handleResourceEvent,
      );
    };
  }, [dataProvider, ingest, commit]);

  // the per-id topics: the backend sends the updates of a process only to
  // the subscribers of its own topic, so the store subscribes to the newest
  // active processes it tracks (bounded: thousands of active processes must
  // not mean thousands of subscription frames; the counts of the app bar are
  // answered by the api regardless)
  const idTopics = useMemo(() => {
    const active = Object.values(state.jobs)
      .filter(isActive)
      .sort((a, b) =>
        String(b.dateCreated ?? "").localeCompare(
          String(a.dateCreated ?? ""),
        ),
      )
      .slice(0, MAX_ID_TOPICS)
      .map(jobId);
    return active;
  }, [state.jobs]);

  useEffect(() => {
    const handleUpdate = (event: CrudEvent): void => {
      if (event.type === "updated") {
        ingest((event.payload.records ?? []) as BackgroundJobRecord[], true);
      }
    };
    const topics = idTopics.map((id) => `resource/BackgroundProcess/${id}`);
    topics.forEach((topic) => void dataProvider.subscribe(topic, handleUpdate));
    return () => {
      topics.forEach((topic) =>
        void dataProvider.unsubscribe(topic, handleUpdate),
      );
    };
  }, [dataProvider, idTopics, ingest]);

  // a burst of created events cannot grow the store unboundedly - and a
  // created event for a process which already moved on is answered by the
  // store's own terminal rule and by this trim
  useEffect(() => {
    const trimmed = trim(stateRef.current);
    if (trimmed !== stateRef.current) {
      commit(trimmed);
    }
  }, [state.jobs, commit]);

  useEffect(() => {
    return () => {
      if (completionTimer.current !== undefined) {
        clearTimeout(completionTimer.current);
      }
    };
  }, []);

  const clearCompleted = useCallback(() => {
    commit(clearCompletedFrom(stateRef.current));
  }, [commit]);

  const value = useMemo<BackgroundJobCenterContextValue>(
    () => ({
      state,
      open,
      setOpen,
      clearCompleted,
    }),
    [state, open, clearCompleted],
  );

  return (
    <BackgroundJobCenterContext.Provider value={value}>
      {children}
      <JobCenterDrawer />
    </BackgroundJobCenterContext.Provider>
  );
};

export default BackgroundJobCenterProvider;
