import { type ReactNode, useCallback, useEffect, useMemo, useRef } from 'react';
import { useDataProvider, useGetList, useNotify, useTranslate } from 'react-admin';
import { ReadyState } from 'react-use-websocket';

import { useHttpClientContext } from '../../../context/HttpClientContext';
import { type CrudEvent } from '../../../providers/dataProvider';
import {
  ACTIVE_STATUSES,
  backgroundJobStore,
  isActiveStatus,
  toJobInput,
  type BackgroundJobStore,
} from './jobsStore';
import { useBackgroundJobs } from './useBackgroundJobs';

/** the resource wide topic carries the created and deleted messages */
export const RESOURCE_TOPIC = 'resource/BackgroundProcess';
/** the per process topic carries every progress update */
export const processTopic = (id: string | number): string =>
  `resource/BackgroundProcess/${id}`;

/** how many running processes the recovery fetch may pull at most. */
export const RECOVERY_PAGE_SIZE = 200;

/** the recovery filter, matching the value the overview filters the active work by */
export const ACTIVE_STATUS_FILTER = ACTIVE_STATUSES.join(',');

/**
 * feed one bus event into the store. Creates and updates carry the record, so
 * they are applied as a live event; a delete drops the job. Events without a
 * record are ignored on purpose: their state is answered by the recovery fetch.
 */
export const ingestEvent = (store: BackgroundJobStore, event: CrudEvent): void => {
  if (event.type === 'delete' || event.type === 'deleted') {
    event.payload.ids.forEach((id) => store.remove(id));
    return;
  }
  event.payload.records?.forEach((record) => {
    const input = toJobInput(record);
    if (input !== undefined) store.apply(input, 'live');
  });
};

export interface BackgroundJobBridgeProps {
  store?: BackgroundJobStore;
}

/**
 * the notification bridge (#1205): it replaces the per-event snackbar flood the
 * former `SnackbarObserver` caused. It subscribes the realtime topics the
 * background jobs publish on - the resource wide one for the creates, one per
 * running process for its progress - and feeds them into the aggregation store.
 * From there it raises a React-Admin notification only when a process becomes
 * actionable, aggregated, so a burst of failures is a single notification.
 *
 * Recovery: on mount it fetches the running processes once, so a reload sees the
 * work already going; when the realtime bus comes back after a drop it refetches,
 * so the failures and completions missed while disconnected are reconciled.
 *
 * It renders nothing.
 */
const BackgroundJobBridge = ({
  store = backgroundJobStore,
}: BackgroundJobBridgeProps): ReactNode => {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const translate = useTranslate();
  const { realtimeIsReady } = useHttpClientContext();

  const handleBusEvent = useCallback((event: CrudEvent) => ingestEvent(store, event), [store]);

  // recovery: the running processes the deployment is busy with right now
  const params = useMemo(
    () => ({
      pagination: { page: 1, perPage: RECOVERY_PAGE_SIZE },
      sort: { field: 'dateCreated', order: 'DESC' as const },
      filter: { status: ACTIVE_STATUS_FILTER },
    }),
    [],
  );
  const { data: seedData, refetch } = useGetList('BackgroundProcess', params);

  useEffect(() => {
    if (!seedData) return;
    const inputs = seedData
      .map((record) => toJobInput(record))
      .filter((input): input is NonNullable<typeof input> => input !== undefined);
    store.seed(inputs);
    // publish the recovered jobs right away instead of waiting for the throttle
    store.flushNow();
  }, [seedData, store]);

  // the running jobs decide which per-process topics must be watched; reading the
  // hook follows the store's coalesced publish. The joined keys are the
  // dependency, so the subscription diff runs only when the running set changes.
  const { jobs } = useBackgroundJobs(store);
  const watchKey = useMemo(
    () =>
      jobs
        .filter((job) => isActiveStatus(job.status))
        .map((job) => String(job.id))
        .sort((a, b) => a.localeCompare(b))
        .join(','),
    [jobs],
  );

  // the resource wide topic is subscribed once for the whole life of the bridge
  useEffect(() => {
    void dataProvider.subscribe(RESOURCE_TOPIC, handleBusEvent);
    return () => {
      void dataProvider.unsubscribe(RESOURCE_TOPIC, handleBusEvent);
    };
  }, [dataProvider, handleBusEvent]);

  // the per-process subscriptions follow the running jobs and are dropped when a
  // process finishes - the subscription count stays bounded by the running jobs
  const watched = useRef(new Map<string, (event: CrudEvent) => void>());
  useEffect(() => {
    const next = new Set(watchKey === '' ? [] : watchKey.split(','));
    watched.current.forEach((callback, id) => {
      if (!next.has(id)) {
        void dataProvider.unsubscribe(processTopic(id), callback);
        watched.current.delete(id);
      }
    });
    next.forEach((id) => {
      if (watched.current.has(id)) return;
      watched.current.set(id, handleBusEvent);
      void dataProvider.subscribe(processTopic(id), handleBusEvent);
    });
  }, [watchKey, dataProvider, handleBusEvent]);

  useEffect(
    () => () => {
      watched.current.forEach((callback, id) =>
        void dataProvider.unsubscribe(processTopic(id), callback),
      );
      watched.current.clear();
    },
    [dataProvider],
  );

  // after a drop the bus knows nothing of what happened while it was down:
  // re-reading the running processes reconciles the missed transitions. The very
  // first connection is already answered by the mount fetch, so only a genuine
  // re-open - an open after a closed connection - refetches.
  const connection = useRef<{ open: boolean; everOpened: boolean }>({
    open: realtimeIsReady === ReadyState.OPEN,
    everOpened: false,
  });
  useEffect(() => {
    const open = realtimeIsReady === ReadyState.OPEN;
    const previous = connection.current;
    if (open && !previous.open && previous.everOpened) {
      void refetch();
    }
    connection.current = { open, everOpened: previous.everOpened || open };
  }, [realtimeIsReady, refetch]);

  // bridge the aggregated failures to a React-Admin notification, once per batch.
  // The translate calls carry the literal keys - a key computed into a variable
  // cannot be traced back to the i18n files - and the finished text goes to notify.
  useEffect(() => {
    return store.subscribeActionable(({ count }) => {
      if (count <= 0) return;
      const message =
        count === 1
          ? translate('backgroundJobs.notification.failedOne', { count })
          : translate('backgroundJobs.notification.failedMany', { count });
      notify(message, { type: 'error' });
    });
  }, [store, notify, translate]);

  return null;
};

export default BackgroundJobBridge;
