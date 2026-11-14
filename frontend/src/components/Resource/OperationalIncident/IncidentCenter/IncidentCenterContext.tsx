import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useDataProvider, useGetList } from "react-admin";

import {
  ACTIVE_INCIDENT_FILTER,
  INCIDENT_POLL_MILLISECONDS,
  INCIDENT_RESOURCE,
  INCIDENT_SORT,
  INCIDENT_WINDOW_SIZE,
  RESOLVED_INCIDENT_FILTER,
  type OperationalIncidentRecord,
} from "../incidentContract";
import IncidentCenterDrawer from "./IncidentCenterDrawer";

/** the resource-wide topic the bus may announce incident changes on; push is
 *  the optional part of #1321, the poll below is the floor */
export const INCIDENT_REALTIME_TOPIC = `resource/${INCIDENT_RESOURCE}`;

/** one server-side window of incidents - the active or the resolved one; its
 *  `total` is the permitted collection total, which is what the badge, the
 *  tab label and the rows of the drawer all agree on (#1321) */
export type IncidentWindow = ReturnType<
  typeof useGetList<OperationalIncidentRecord>
>;

export interface IncidentCenterContextValue {
  /** the incidents which still ask for attention */
  active: IncidentWindow;
  /** the incidents recovery decided, newest activity first */
  resolved: IncidentWindow;
  /** whether the drawer is open */
  open: boolean;
  setOpen: (open: boolean) => void;
}

const IncidentCenterContext = createContext<
  IncidentCenterContextValue | undefined
>(undefined);

export const useIncidentCenter = (): IncidentCenterContextValue => {
  const context = useContext(IncidentCenterContext);
  if (context === undefined) {
    throw new Error(
      "useIncidentCenter must be used inside an IncidentCenterProvider",
    );
  }
  return context;
};

/**
 * The single client-side state of the Incident Center (#1321).
 *
 * Two bounded windows of the incident api - the active and the resolved one -
 * are read once here and shared by the app bar indicator and the drawer, so
 * the global count and the list cannot disagree: both are the same permitted
 * JSON:API result. Permission filtering is the server's (#1319); nothing here
 * knows who may see what, and no private title, id or partial count can
 * reach a client through this code.
 *
 * The cadence is bounded in two directions: `refetchInterval` polls at
 * INCIDENT_POLL_MILLISECONDS and react-query owns its lifecycle - unmounting
 * stops it, which is the cleanup #1321 asks for - while a message on the
 * resource-wide topic shortens the distance to zero for that one moment.
 * Until #1319 merged, every read ends in an error; the consumers treat that
 * as silence, so the app bar gains an invisible no-op instead of a broken
 * widget.
 *
 * Deliberately absent: any `useNotify`. An incident announces itself through
 * this center; a snackbar per incident is the flooding #1321 forbids, and
 * the existing notification path of react-admin keeps working untouched.
 */
export const IncidentCenterProvider = ({
  children,
}: {
  children: ReactNode;
}): ReactNode => {
  const dataProvider = useDataProvider();
  const [open, setOpen] = useState(false);

  const active = useGetList<OperationalIncidentRecord>(
    INCIDENT_RESOURCE,
    {
      filter: ACTIVE_INCIDENT_FILTER,
      sort: INCIDENT_SORT,
      pagination: { page: 1, perPage: INCIDENT_WINDOW_SIZE },
    },
    { refetchInterval: INCIDENT_POLL_MILLISECONDS, retry: false },
  );
  const resolved = useGetList<OperationalIncidentRecord>(
    INCIDENT_RESOURCE,
    {
      filter: RESOLVED_INCIDENT_FILTER,
      sort: INCIDENT_SORT,
      pagination: { page: 1, perPage: INCIDENT_WINDOW_SIZE },
    },
    { refetchInterval: INCIDENT_POLL_MILLISECONDS, retry: false },
  );

  // the optional push (#1321): the bus only says that something moved, the
  // windows are rebuilt by the api - the same recovery the Job Center
  // practices, with the poll as the floor when nothing pushes
  useEffect(() => {
    const refresh = () => {
      void active.refetch();
      void resolved.refetch();
    };
    void dataProvider.subscribe(INCIDENT_REALTIME_TOPIC, refresh);
    return () => {
      void dataProvider.unsubscribe(INCIDENT_REALTIME_TOPIC, refresh);
    };
  }, [dataProvider, active.refetch, resolved.refetch]);

  const value = useMemo<IncidentCenterContextValue>(
    () => ({ active, resolved, open, setOpen }),
    [active, resolved, open],
  );

  return (
    <IncidentCenterContext.Provider value={value}>
      {children}
      <IncidentCenterDrawer />
    </IncidentCenterContext.Provider>
  );
};

export default IncidentCenterProvider;
