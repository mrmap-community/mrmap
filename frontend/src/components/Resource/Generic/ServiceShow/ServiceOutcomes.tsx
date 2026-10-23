import {
  DateField,
  type RaRecord,
  RecordContextProvider,
  useGetList,
  useRecordContext,
  useResourceContext,
  useTranslate,
} from "react-admin";

import { Stack, Typography } from "@mui/material";

interface OutcomeProps {
  /** what is asked about, translated */
  label: string;
  /** the newest run or job of the service, which the api answers as its own record */
  outcome?: RaRecord;
  /** the attribute of the record which names the point in time it was done at */
  dateSource: string;
  /** whether the run or job is still asked for */
  pending: boolean;
  /** whether asking for the run or job failed */
  failed: boolean;
}

/**
 * One line which answers the newest run or job of a service.
 *
 * The date is the point in time the run or job was done at and the state is the
 * one the api answers for it. A service which never ran and was never updated
 * answers no record, which is said instead of an empty line, and a record which
 * is not readable for the user is not pretended to be absent.
 */
const OutcomeLine = ({
  label,
  outcome,
  dateSource,
  pending,
  failed,
}: OutcomeProps) => {
  const translate = useTranslate();
  const state =
    outcome?.success !== undefined
      ? translate(
          `serviceShow.outcome.${outcome.success ? "passed" : "failed"}`,
        )
      : outcome?.status;
  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: "baseline" }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      {failed ? (
        <Typography variant="body2">
          {translate("serviceShow.outcome.unavailable")}
        </Typography>
      ) : pending ? (
        <Typography variant="body2">
          {translate("serviceShow.outcome.asking")}
        </Typography>
      ) : outcome?.[dateSource] ? (
        <RecordContextProvider value={outcome}>
          <DateField
            source={dateSource}
            showTime
            sx={{ variant: "body2", overflowWrap: "anywhere" }}
          />
          {state && (
            <Typography variant="body2" color="text.secondary">
              {`· ${state}`}
            </Typography>
          )}
        </RecordContextProvider>
      ) : (
        <Typography variant="body2">
          {translate("serviceShow.outcome.none")}
        </Typography>
      )}
    </Stack>
  );
};

/**
 * The latest operational outcome of the service of the record context.
 *
 * A service answers the states which hurt as attributes of itself, but not the
 * run or job which came in time: those are asked here, one record each, and
 * only while a service is shown. The run of a service is read at the endpoint
 * of the runs of that service and its update job at the jobs of that service,
 * which are the endpoints the overview of a service asks its runs and jobs at
 * too.
 */
const ServiceOutcomes = () => {
  const resource = useResourceContext();
  const service = useRecordContext();
  const translate = useTranslate();
  const asked = {
    pagination: { page: 1, perPage: 1 },
    filter: {},
    meta: { relatedResource: { resource, id: service?.id } },
  };
  const runs = useGetList(
    `${resource}MonitoringRun`,
    { ...asked, sort: { field: "dateDone", order: "DESC" } },
    { enabled: Boolean(resource && service?.id), retry: false },
  );
  const jobs = useGetList(
    `${resource}UpdateJob`,
    {
      ...asked,
      filter: { done_at__isnull: false },
      sort: { field: "doneAt", order: "DESC" },
    },
    { enabled: Boolean(resource && service?.id), retry: false },
  );

  return (
    <Stack spacing={0}>
      <OutcomeLine
        label={translate("serviceShow.outcome.lastMonitoring")}
        outcome={runs.data?.[0]}
        dateSource="dateDone"
        pending={runs.isPending}
        failed={Boolean(runs.error)}
      />
      <OutcomeLine
        label={translate("serviceShow.outcome.lastUpdate")}
        outcome={jobs.data?.[0]}
        dateSource="doneAt"
        pending={jobs.isPending}
        failed={Boolean(jobs.error)}
      />
    </Stack>
  );
};

export default ServiceOutcomes;
