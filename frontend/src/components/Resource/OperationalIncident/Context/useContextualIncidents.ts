import { useEffect, useMemo } from "react";
import { useDataProvider, useGetList } from "react-admin";

import {
  ACTIVE_INCIDENT_FILTER,
  INCIDENT_POLL_MILLISECONDS,
  INCIDENT_RESOURCE,
  INCIDENT_SORT,
  INCIDENT_WINDOW_SIZE,
  RESOLVED_INCIDENT_FILTER,
  type IncidentSeverity,
  type OperationalIncidentRecord,
} from "../incidentContract";

/** the resource-wide topic the bus may announce incident changes on; the same
 *  string the Incident Center (#1321) subscribes to - push shortens the wait,
 *  the poll below is the floor (#1321: the incident api may not push at all) */
const INCIDENT_REALTIME_TOPIC = `resource/${INCIDENT_RESOURCE}`;

/** whether an incident is about this very record
 *
 *  The api answers `affectedResource` as the type and id of the resource the
 *  incident stands for, and it answers the incidents of resources this caller
 *  may view alone - the narrowing of `visible_for_user` is the list itself
 *  (#1319) - so an answered pair is always one this screen may show, and a
 *  system incident, which answers no pair, is never a match. The client never
 *  derives a destination it was not answered. */
export const aboutRecord = (
  record: OperationalIncidentRecord,
  resource?: string,
  id?: string | number,
): boolean => {
  const affected = record.affectedResource;
  if (!resource || id === undefined || id === null || !affected) return false;
  return affected.type === resource && String(affected.id) === String(id);
};

const SEVERITY_RANK: Record<IncidentSeverity, number> = { error: 0, warning: 1 };

/** errors above warnings, then newest activity first */
const bySeverityThenRecent = (
  a: OperationalIncidentRecord,
  b: OperationalIncidentRecord,
): number => {
  const severity = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
  if (severity !== 0) return severity;
  return (
    new Date(b.lastOccurredAt).getTime() -
    new Date(a.lastOccurredAt).getTime()
  );
};

/** one entry per incident identity - the api folds retries into a row, but a
 *  client never draws the same incident twice even if a window repeats it */
const uniqueById = (
  records: OperationalIncidentRecord[],
): OperationalIncidentRecord[] => {
  const seen = new Set<string>();
  return records.filter(
    (record) =>
      seen.has(String(record.id)) ? false : seen.add(String(record.id)) != null,
  );
};

export interface ContextualIncidents {
  /** the active incidents about this record, most severe first */
  active: OperationalIncidentRecord[];
  /** the resolved incidents about this record, newest activity first */
  resolved: OperationalIncidentRecord[];
  /** the read of the active window is still on its way */
  isPending: boolean;
  /** the incident api could not be read - which is silence, never an alarm */
  error: unknown;
}

/**
 * The operational incidents about one record, for its detail page (#1322).
 *
 * The two windows of the incident api - the active and the resolved one -
 * are read with the ONE lifecycle facet the api declares (`status`, #1319)
 * and matched to the record of the screen client-side by the
 * `affectedResource` the api answers. Permission filtering stays entirely
 * server side - a row this reader may not see is not in the window at all
 * (`visible_for_user`), and a system incident answers no resource to match
 * against - so no private incident, count or destination reaches a client
 * through this hook. The filterset also declares the typed resource facets
 * which would scope these queries server-side; asking them is a #1322
 * follow-up bounded by a behave scenario, not an assumption made here
 * (#1080).
 *
 * A read which fails - the service briefly unreachable, the session ended -
 * is reported to the caller as silence, exactly as the Incident Center
 * (#1321) treats it, so a detail page gains nothing invisible rather than a
 * broken banner.
 */
const useContextualIncidents = ({
  resource,
  id,
}: {
  resource?: string;
  id?: string | number;
}): ContextualIncidents => {
  const dataProvider = useDataProvider();
  const enabled = !!resource && id !== undefined && id !== null;

  const activeWindow = useGetList<OperationalIncidentRecord>(
    INCIDENT_RESOURCE,
    {
      filter: ACTIVE_INCIDENT_FILTER,
      sort: INCIDENT_SORT,
      pagination: { page: 1, perPage: INCIDENT_WINDOW_SIZE },
    },
    { enabled, retry: false, refetchInterval: INCIDENT_POLL_MILLISECONDS },
  );
  const resolvedWindow = useGetList<OperationalIncidentRecord>(
    INCIDENT_RESOURCE,
    {
      filter: RESOLVED_INCIDENT_FILTER,
      sort: INCIDENT_SORT,
      pagination: { page: 1, perPage: INCIDENT_WINDOW_SIZE },
    },
    { enabled, retry: false, refetchInterval: INCIDENT_POLL_MILLISECONDS },
  );

  // the optional push: the bus only says something moved, the windows are
  // rebuilt by the api - the recovery the Incident Center and the job center
  // practice, with the poll as the floor when nothing pushes
  // the refetch callbacks are stable per query, so the bus is re-subscribed
  // only when the identity of the screen or its query changes - not on every
  // poll - the recovery the Incident Center (#1321) practices
  const { refetch: refetchActiveWindow } = activeWindow;
  const { refetch: refetchResolvedWindow } = resolvedWindow;
  useEffect(() => {
    if (!enabled) return;
    const refresh = () => {
      void refetchActiveWindow();
      void refetchResolvedWindow();
    };
    void dataProvider.subscribe(INCIDENT_REALTIME_TOPIC, refresh);
    return () => {
      void dataProvider.unsubscribe(INCIDENT_REALTIME_TOPIC, refresh);
    };
  }, [dataProvider, enabled, refetchActiveWindow, refetchResolvedWindow]);

  const active = useMemo(
    () =>
      uniqueById(
        (activeWindow.data ?? []).filter((record) =>
          aboutRecord(record, resource, id),
        ),
      ).sort(bySeverityThenRecent),
    [activeWindow.data, resource, id],
  );
  const resolved = useMemo(
    () =>
      uniqueById(
        (resolvedWindow.data ?? []).filter((record) =>
          aboutRecord(record, resource, id),
        ),
      ).sort(bySeverityThenRecent),
    [resolvedWindow.data, resource, id],
  );

  return {
    active,
    resolved,
    isPending: activeWindow.isPending,
    error: activeWindow.error ?? resolvedWindow.error,
  };
};

export default useContextualIncidents;
