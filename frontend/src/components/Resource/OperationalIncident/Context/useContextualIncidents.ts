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

/** the (resource, id) a `targetPath` names, or nothing when it names none
 *
 *  The api answers `targetPath` as the show path of the affected resource -
 *  the same answer `ListServiceAlert` navigates on - as
 *  `/<Resource>/<id>/show`, optionally continued by a tab. Only that identity
 *  is read here; the client never derives a path it was not given. */
export const parseTargetKey = (
  targetPath?: string | null,
): { resource: string; id: string } | null => {
  if (!targetPath) return null;
  const match = /\/([^/]+)\/([^/]+)\/show(?:[/?#]|$)/.exec(targetPath);
  if (!match) return null;
  return { resource: match[1], id: match[2] };
};

/** whether an incident is about this very record
 *
 *  A row whose `targetPath` is absent is not about anything this client may
 *  open - #1319 answers the path only when the reader is permitted to the
 *  affected resource - so it is never a match, which is how a private incident
 *  cannot surface on a page it does not belong to. */
const targetsRecord = (
  record: OperationalIncidentRecord,
  resource?: string,
  id?: string | number,
): boolean => {
  if (!resource || id === undefined || id === null) return false;
  const key = parseTargetKey(record.targetPath);
  return (
    !!key && key.resource === resource && key.id === String(id)
  );
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
    new Date(b.lastOccurrence).getTime() -
    new Date(a.lastOccurrence).getTime()
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
 * The two windows of the incident api - the active and the resolved one - are
 * read with the ONE filter facet the api declares (`state`) and matched to the
 * record of the screen client-side by the `targetPath` the api answers. This is
 * deliberate: a `filter[target]` this screen invented would be an api contract
 * #1319 has not declared, and an undeclared facet is answered with a 400, never
 * ignored (#1080). Permission filtering stays entirely server side - a row this
 * reader may not see is not in the window at all, and a row whose `targetPath`
 * is withheld matches nothing - so no private incident, count or path reaches a
 * client through this hook.
 *
 * Until #1319 is merged every read ends in an error; the caller treats that as
 * silence, exactly as the Incident Center (#1321) does, so a detail page gains
 * nothing invisible rather than a broken banner.
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
  useEffect(() => {
    if (!enabled) return;
    const refresh = () => {
      void activeWindow.refetch();
      void resolvedWindow.refetch();
    };
    void dataProvider.subscribe(INCIDENT_REALTIME_TOPIC, refresh);
    return () => {
      void dataProvider.unsubscribe(INCIDENT_REALTIME_TOPIC, refresh);
    };
    // the refetch callbacks are stable per query, so the bus is re-subscribed
    // only when the identity of the screen or its query changes - not on every
    // poll - the recovery the Incident Center (#1321) practices
  }, [dataProvider, enabled, activeWindow.refetch, resolvedWindow.refetch]);

  const active = useMemo(
    () =>
      uniqueById(
        (activeWindow.data ?? []).filter((record) =>
          targetsRecord(record, resource, id),
        ),
      ).sort(bySeverityThenRecent),
    [activeWindow.data, resource, id],
  );
  const resolved = useMemo(
    () =>
      uniqueById(
        (resolvedWindow.data ?? []).filter((record) =>
          targetsRecord(record, resource, id),
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
