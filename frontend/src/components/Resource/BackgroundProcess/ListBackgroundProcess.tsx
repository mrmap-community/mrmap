import { type ReactNode } from "react";
import { RaRecord } from "react-admin";
import { ReadyState } from "react-use-websocket";

import { type AlertColor } from "@mui/material/Alert";

import { useHttpClientContext } from "../../../context/HttpClientContext";
import ListWithDialogs from "../../../jsonapi/components/ListWithDialogs";
import DurationField from "../../Field/DurationField";
import ProgressField from "../../Field/ProgressField";
import RelatedResourceField from "../../Field/RelatedResourceField";
import ProcessStatusField from "./ProcessStatusField";

/** the processes the overview answers by default: the work which did not end yet */
export const ACTIVE_STATUSES = "pending,running";

const getColor = (record: RaRecord): AlertColor => {
  switch (record?.status) {
    case "completed":
      return "success";
    case "failed":
      return "error";
    case "aborted":
      return "warning";
    default:
      return "info";
  }
};

/**
 * The processes the background of the deployment is running or has run.
 *
 * The screen renders its list through `ListWithDialogs` - the way the service
 * lists, the update settings and the catalogue update jobs do - because the EDIT
 * button of a row navigates to `/BackgroundProcess/<id>`, the URL pattern every
 * resource's edit dialog follows, and a process is writable over the api: the
 * abort of a row is a PATCH of it. `ListGuesser` alone keeps answering that URL
 * with the list and leaves the offered action without an editor (#1275).
 */
const ListBackgroundProcess = (): ReactNode => {
  // the realtime bus reports every change of the listed processes, the interval
  // is only the fallback while it is not connected
  const { realtimeIsReady } = useHttpClientContext();
  return (
    <ListWithDialogs
      listGuesserProps={{
        realtime: true,
        resource: "BackgroundProcess",
        // the overview is about what the deployment is doing right now, so it
        // starts with the processes which did not end yet, newest first. The
        // filter is a default which the user may change to look back
        filterDefaultValues: { status: ACTIVE_STATUSES },
        sort: { field: "dateCreated", order: "DESC" },
        perPage: 25,
        defaultSelectedColumns: [
          "description",
          "processType",
          "phase",
          "status",
          "progress",
          "dateCreated",
          "doneAt",
          "duration",
          "relatedResource",
          "actions",
        ],
        updateFieldDefinitions: [
          {
            component: ProgressField,
            props: { source: "progress", getColor: getColor },
          },
          {
            component: ProcessStatusField,
            props: { source: "status" },
          },
          {
            component: DurationField,
            props: { source: "duration" },
          },
          {
            component: RelatedResourceField,
            props: { source: "relatedResource" },
          },
        ],
        refetchInterval: realtimeIsReady === ReadyState.OPEN ? false : 20000,
      }}
    />
  );
};

export default ListBackgroundProcess;
