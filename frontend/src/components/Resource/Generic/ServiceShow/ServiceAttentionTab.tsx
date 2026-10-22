import { useEffect, type ReactNode } from "react";
import {
  BasenameContextProvider,
  type RaRecord,
  DateField,
  ShowButton,
  useRecordContext,
  useRefresh,
  useResourceContext,
  useResourceDefinitions,
  useTranslate,
} from "react-admin";

import { Alert, Stack, Typography } from "@mui/material";

/** the interval the attention of a service is asked for again, in milliseconds */
export const ATTENTION_REFETCH_INTERVAL = 60000;

export interface ServiceAlert {
  /** the attribute which answers whether the state needs attention */
  flag: string;
  /** the attribute which answers the point in time the state appeared at */
  at?: string;
  /** the key which names what the point in time of the state is */
  atLabel?: string;
  /** the attribute which names the record which decided the state */
  reference?: string;
  /** the kind of record which decided the state */
  target?: "MonitoringRun" | "UpdateJob" | "HarvestingJob";
  /** how much attention the state needs */
  severity: "error" | "warning";
}

/**
 * The states of a service which an administrator has to attend to, the states
 * which hurt first. Only a catalogue answers the state of its harvesting, which
 * no other kind of service has - an attribute a record does not answer is not
 * shown.
 *
 * Next to a state, an alert names the record which decided it (`reference`) and
 * the kind of record that is (`target`), so that an administrator is asked to
 * look at the failing run or job instead of searching it.
 */
export const SERVICE_ALERTS: ServiceAlert[] = [
  {
    flag: "monitoringFailed",
    at: "monitoringFailedAt",
    atLabel: "lastRunDone",
    reference: "monitoringFailedRun",
    target: "MonitoringRun",
    severity: "error",
  },
  {
    flag: "updateFailed",
    at: "updateFailedAt",
    atLabel: "lastUpdateDone",
    reference: "updateFailedJob",
    target: "UpdateJob",
    severity: "error",
  },
  {
    flag: "harvestAborted",
    at: "harvestFailedAt",
    atLabel: "harvestDone",
    reference: "harvestJob",
    target: "HarvestingJob",
    severity: "error",
  },
  {
    flag: "updateReviewRequired",
    at: "updateReviewRequiredAt",
    atLabel: "waitingSince",
    reference: "updateReviewJob",
    target: "UpdateJob",
    severity: "warning",
  },
  {
    flag: "harvestIncomplete",
    at: "harvestFailedAt",
    atLabel: "harvestDone",
    reference: "harvestJob",
    target: "HarvestingJob",
    severity: "warning",
  },
];

/** the resource of the record which decided an alert of a service
 *
 * A monitoring run and an update job are named after the kind of the service they
 * belong to, while a harvesting job is a resource of its own which belongs to the
 * catalogue that ran it.
 */
const alertResource = (service: string, target?: ServiceAlert["target"]) =>
  target === "HarvestingJob" ? target : `${service}${target}`;

interface ServiceAlertRecordProps {
  /** the kind of the service the alert was answered for */
  service: string;
  /** the alert which was answered about the service */
  alert: ServiceAlert;
  /** the record which decided the alert, as the service answered it */
  recordId?: string | number;
}

/**
 * The way to the record which decided an alert.
 *
 * The api answers an alert with the identifier of the record behind it alone, so
 * that record is read at the endpoint of its own kind - which means a client which
 * may not read it is answered the alert of its service and nothing more. An alert
 * without a record behind it is asked about at the service itself, as the update
 * of a dangling candidate is: nothing is linked then.
 */
const ServiceAlertRecord = ({
  service,
  alert,
  recordId,
}: ServiceAlertRecordProps) => {
  const translate = useTranslate();
  const definitions = useResourceDefinitions();
  const resource = alert.target && alertResource(service, alert.target);
  // a record named by its identifier alone is read at the screen of its own kind,
  // which this deployment does not have for every kind of record: the update of a
  // catalogue has none
  const shown = resource ? definitions[resource]?.hasShow : undefined;
  if (
    !resource ||
    shown === undefined ||
    recordId === undefined ||
    recordId === null
  ) {
    return (
      <Typography variant="body2">
        {translate("serviceAttention.noRecord")}
      </Typography>
    );
  }
  return (
    // the screen of a service is the base of the paths of its own tabs, the
    // record behind an alert is shown at a screen of a kind of its own
    <BasenameContextProvider basename="">
      <ShowButton
        resource={resource}
        record={{ id: recordId }}
        label={`serviceAttention.records.${alert.target}`}
        size="small"
      />
    </BasenameContextProvider>
  );
};

/**
 * Tab which lists the attention the shown service needs.
 *
 * The alerts of a service are attributes of the service itself, answered by
 * annotations of the services and not by a resource of their own, which means
 * that this tab reads the record of the service it is shown for. An alert
 * disappears as soon as the state behind it is fixed, and nothing is pushed
 * about a state which no row stores - so this tab asks for the service again
 * from time to time.
 */
export const ServiceAttentionTab = (): ReactNode => {
  const record = useRecordContext();
  const service = useResourceContext();
  const translate = useTranslate();
  const refresh = useRefresh();

  useEffect(() => {
    const interval = setInterval(refresh, ATTENTION_REFETCH_INTERVAL);
    return () => clearInterval(interval);
  }, [refresh]);

  const alerts = SERVICE_ALERTS.filter((alert) =>
    Boolean((record as RaRecord | undefined)?.[alert.flag]),
  );

  if (alerts.length === 0) {
    return (
      <Alert severity="success">{translate("serviceAttention.none")}</Alert>
    );
  }

  return (
    <Stack spacing={1.5}>
      {alerts.map((alert) => {
        // a date is only shown with the state it belongs to, and only when the
        // service answered the point in time of that state - and it is named by
        // what it is: the end of the run or job which found the state, which is
        // not the point in time the state began to hurt
        const source = alert.at && record?.[alert.at] ? alert.at : undefined;
        return (
          <Alert key={alert.flag} severity={alert.severity}>
            {translate(`serviceAttention.alerts.${alert.flag}`)}
            {source && (
              <Stack direction="row" spacing={0.5}>
                <span>
                  {translate(`serviceAttention.dates.${alert.atLabel}`)}
                </span>
                <DateField source={source} showTime />
              </Stack>
            )}
            {alert.reference && service && (
              <ServiceAlertRecord
                service={service}
                alert={alert}
                recordId={record?.[alert.reference] as string | number}
              />
            )}
          </Alert>
        );
      })}
    </Stack>
  );
};

export default ServiceAttentionTab;
