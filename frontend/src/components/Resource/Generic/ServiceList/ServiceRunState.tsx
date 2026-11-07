import {
  type Identifier,
  type RaRecord,
  ShowButton,
  useRecordContext,
  useTranslate,
} from "react-admin";

import { Stack, Typography } from "@mui/material";

import RelativeDateField from "../../../Field/RelativeDateField";
import { SERVICE_ALERTS } from "../ServiceShow/ServiceAttentionTab";

export interface RunningRunOfAService {
  /** the property of the service which answers the run which is working right now */
  source: string;
  /** the resource which shows that run */
  resource: string;
  /** the key which names the way to it */
  label: string;
}

export interface ServiceRunStateProps {
  /** the states of attention this column answers, as SERVICE_ALERTS names them */
  flags: string[];
  /** the run of this kind which the service may answer as working right now -
   *  unset for a kind of run which is never shown as working */
  running?: RunningRunOfAService;
  /** the locale the moment of a state is formatted with */
  locales?: string;
  /** the service to answer, the record of the screen if unset */
  record?: RaRecord;
}

/**
 * What the runs of one kind of a service left behind, read from the row itself.
 *
 * The states which hurt and the moment the run which decided them ended are
 * annotations of the service (registry/querys/alerts.py), so a page of services
 * costs no request per row - which is what this column is for and why it is not
 * `ServiceOutcomes`: that component asks the newest run and the newest update job
 * of one *shown* service, one request each, and cannot answer a page of rows
 * without one request per row. Neither is it `ServiceAlertChips`, which names the
 * states of a service together in one compact chip per state and answers no
 * moment at all.
 *
 * A state which the service does not answer is not shown, so the states of the
 * harvesting stay out of the row of a kind of service which is not harvested -
 * the same rule the chips and the attention tab of a service follow. A row which
 * answers nothing says so, because an empty cell of a column which shows the
 * states which hurt is read as a health the api never promised.
 */
const ServiceRunState = ({
  flags,
  running,
  locales,
  record,
}: ServiceRunStateProps) => {
  const contextService = useRecordContext<RaRecord>();
  const translate = useTranslate();
  const service = record ?? contextService;

  const alerts = SERVICE_ALERTS.filter(
    (alert) => flags.includes(alert.flag) && Boolean(service?.[alert.flag]),
  );
  const runningJob = running
    ? (service?.[running.source] as { id?: Identifier } | undefined)
    : undefined;

  if (alerts.length === 0 && runningJob?.id === undefined) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("serviceList.nothingReported")}
      </Typography>
    );
  }

  return (
    <Stack spacing={0} sx={{ alignItems: "flex-start" }}>
      {alerts.map((alert) => {
        // the moment belongs to the state: it is the end of the run which decided
        // that state and it is answered with no other state
        const moment =
          alert.at && service?.[alert.at] !== undefined ? alert.at : undefined;
        return (
          <Stack key={alert.flag} direction="row" spacing={0.5}>
            <Typography
              variant="body2"
              color={alert.severity === "error" ? "error.main" : "warning.main"}
              sx={{ whiteSpace: "nowrap" }}
            >
              {translate(`serviceAttention.shortLabels.${alert.flag}`)}
            </Typography>
            {moment !== undefined && (
              <RelativeDateField source={moment} locales={locales} />
            )}
          </Stack>
        );
      })}
      {running && runningJob?.id !== undefined && (
        <ShowButton
          resource={running.resource}
          record={{ id: runningJob.id }}
          label={running.label}
          size="small"
        />
      )}
    </Stack>
  );
};

export default ServiceRunState;
