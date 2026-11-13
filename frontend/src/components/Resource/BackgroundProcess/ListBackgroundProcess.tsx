import { type ReactNode } from "react";
import { FunctionField, RaRecord, useTranslate } from "react-admin";
import { ReadyState } from "react-use-websocket";

import { type AlertColor } from "@mui/material/Alert";

import { useHttpClientContext } from "../../../context/HttpClientContext";
import ListGuesser from "../../../jsonapi/components/ListGuesser";
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

const ListBackgroundProcess = (): ReactNode => {
  // the realtime bus reports every change of the listed processes, the interval
  // is only the fallback while it is not connected
  const { realtimeIsReady } = useHttpClientContext();
  const translate = useTranslate();
  return (
    <ListGuesser
      realtime={true}
      resource="BackgroundProcess"
      // the overview is about what the deployment is doing right now, so it
      // starts with the processes which did not end yet, newest first. The
      // filter is a default which the user may change to look back
      filterDefaultValues={{ status: ACTIVE_STATUSES }}
      sort={{ field: "dateCreated", order: "DESC" }}
      perPage={25}
      defaultSelectedColumns={[
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
      ]}
      updateFieldDefinitions={[
        {
          component: ProgressField,
          props: { source: "progress", getColor: getColor },
        },
        {
          component: ProcessStatusField,
          props: { source: "status" },
        },
        {
          // the phase is a key reported by the api, looked up in the
          // background activity translations; values which are not keys -
          // error texts, phases of process types this change did not reach -
          // answer raw, as before (#1267)
          component: FunctionField,
          props: {
            source: "phase",
            render: (record: RaRecord) =>
              typeof record?.phase === "string" && record.phase !== ""
                ? translate(`backgroundActivity.phases.${record.phase}`, {
                    _: record.phase,
                  })
                : undefined,
          },
        },
        {
          component: DurationField,
          props: { source: "duration" },
        },
        {
          component: RelatedResourceField,
          props: { source: "relatedResource" },
        },
      ]}
      refetchInterval={realtimeIsReady === ReadyState.OPEN ? false : 20000}
    />
  );
};

export default ListBackgroundProcess;
