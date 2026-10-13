import { Alert, Stack } from "@mui/material";
import { useEffect, type ReactNode } from "react";
import {
  type RaRecord,
  DateField,
  useRecordContext,
  useRefresh,
  useTranslate,
} from "react-admin";

/** the interval the attention of a service is asked for again, in milliseconds */
export const ATTENTION_REFETCH_INTERVAL = 60000;

interface ServiceAlert {
  /** the attribute which answers whether the state needs attention */
  flag: string;
  /** the attribute which answers the point in time the state appeared at */
  at?: string;
  /** how much attention the state needs */
  severity: "error" | "warning";
}

/**
 * The states of a service which an administrator has to attend to, the states
 * which hurt first. Only a catalogue answers the state of its harvesting, which
 * no other kind of service has - an attribute a record does not answer is not
 * shown.
 */
export const SERVICE_ALERTS: ServiceAlert[] = [
  { flag: "monitoringFailed", at: "monitoringFailedAt", severity: "error" },
  { flag: "updateFailed", at: "updateFailedAt", severity: "error" },
  { flag: "harvestAborted", at: "harvestFailedAt", severity: "error" },
  {
    flag: "updateReviewRequired",
    at: "updateReviewRequiredAt",
    severity: "warning",
  },
  { flag: "harvestIncomplete", at: "harvestFailedAt", severity: "warning" },
];

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
  const translate = useTranslate();
  const refresh = useRefresh();

  useEffect(() => {
    const interval = setInterval(refresh, ATTENTION_REFETCH_INTERVAL);
    return () => clearInterval(interval);
  }, [refresh]);

  const alerts = SERVICE_ALERTS.filter(
    (alert) => Boolean((record as RaRecord | undefined)?.[alert.flag]),
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
        // service answered the point in time of that state
        const source = alert.at && record?.[alert.at] ? alert.at : undefined;
        return (
          <Alert key={alert.flag} severity={alert.severity}>
            {translate(`serviceAttention.alerts.${alert.flag}`)}
            {source && (
              <Stack direction="row" spacing={0.5}>
                <span>{translate("serviceAttention.at")}</span>
                <DateField source={source} showTime />
              </Stack>
            )}
          </Alert>
        );
      })}
    </Stack>
  );
};

export default ServiceAttentionTab;
