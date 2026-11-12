import { useRef } from "react";
import {
  BooleanField,
  DateField,
  FunctionField,
  Labeled,
  Link,
  Loading,
  NumberField,
  SimpleShowLayout,
  TabbedShowLayout,
  TextField,
  useCreatePath,
  useGetList,
  useShowContext,
  useTranslate,
} from "react-admin";

import {
  Alert,
  Card,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import ListHarvestingLog from "../HarvestingLog/ListHarvestingLog";
import HarvestingJobTimingCharts from "./HarvestingJobTimingCharts";
import HarvestingRunMissingRecords from "./HarvestingRunMissingRecords";
import HarvestingRunSummary from "./HarvestingRunSummary";
import { formatMeasuredDuration, formatSeconds } from "./runDurations";

/** whether an api error says the caller may not read what was asked for */
const isForbidden = (error: unknown): boolean => {
  const e = error as { status?: number; response?: { status?: number } };
  return e?.status === 403 || e?.response?.status === 403;
};

// The run answers these counts of every kind it collects (see
// registry.serializers.harvesting.HarvestingJobSerializer): the names are the
// presentation choice of this table, the numbers and their labels stay schema-owned.
const RESULT_COUNT_STATES = ["new", "updated", "existing", "duplicated"];
const RESULT_COUNT_KINDS = [
  { label: "datasets", prefix: "Dataset" },
  { label: "services", prefix: "Service" },
  { label: "applications", prefix: "Application" },
];

const HarvestingJobTabbedShowLayout = () => {
  const { record, isPending, error } = useShowContext();
  const translate = useTranslate();
  const createPath = useCreatePath();
  // a caller may read a run and still be denied its log lines - the counts
  // are answered by the run, the lines are not, so whether the tab is there
  // is answered by the nested route itself and not guessed from a role
  // (#1083). one row is enough to learn the verdict, and a denial which is
  // not about permission still opens the tab: only the 403 means absent
  const {
    isPending: logProbePending,
    error: logProbeError,
  } = useGetList(
    "HarvestingLog",
    {
      pagination: { page: 1, perPage: 1 },
      sort: { field: "timestamp", order: "DESC" },
      meta: {
        relatedResource: { resource: "HarvestingJob", id: record?.id },
      },
    },
    { enabled: !isPending && !!record && !error, retry: false },
  );
  // the websocket payload of a run carries its progress and its measurements,
  // but not the statistics of its records: the push would blank the measured
  // durations until the next poll. A measured duration never gets smaller, so
  // the value this screen has last read stays true until a poll refreshes it
  // (#1071)
  const carriedDurations = useRef<Record<string, string>>({});
  if (record?.fetchRecordDuration)
    carriedDurations.current.fetchRecordDuration = record.fetchRecordDuration;
  if (record?.mdMetadataFileToDbDuration)
    carriedDurations.current.mdMetadataFileToDbDuration =
      record.mdMetadataFileToDbDuration;
  if (error) {
    return (
      <Alert severity="error">
        {translate("harvestingActivity.loadError")}
      </Alert>
    );
  }
  if (isPending || !record) return <Loading />;
  const path = createPath({
    resource: "HarvestingJob",
    id: record.id,
    type: "show",
  });
  const logTabAllowed = !logProbePending && !isForbidden(logProbeError);
  return (
    <Stack spacing={2} sx={{ p: { xs: 1, md: 2 } }}>
      <HarvestingRunSummary logTabAllowed={logTabAllowed} />
      <Card variant="outlined">
        <TabbedShowLayout>
          <TabbedShowLayout.Tab label="harvestRun.overview">
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="h6">
                  {translate("harvestRun.configuration")}
                </Typography>
                <SimpleShowLayout>
                  <JsonApiReferenceField
                    source="service"
                    reference="CatalogueService"
                  />
                  <BooleanField source="harvestDatasets" />
                  <BooleanField source="harvestServices" />
                  <BooleanField source="harvestApplications" />
                </SimpleShowLayout>
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="h6">
                  {translate("harvestRun.status")}
                </Typography>
                <SimpleShowLayout>
                  <TextField source="phaseLabel" label="harvestRun.phase" />
                  <NumberField source="totalRecords" />
                  {/* the counts of what a run left behind are links into the
                      tab which names those records - a count an administrator
                      cannot click is a number they cannot act on (#1083) */}
                  <FunctionField
                    source="unhandledRecordsCount"
                    label="harvestRun.unhandled"
                    render={(r) =>
                      r.unhandledRecordsCount != null ? (
                        <Link to={`${path}/failed-records`}>
                          {r.unhandledRecordsCount}
                        </Link>
                      ) : null
                    }
                  />
                  <FunctionField
                    source="importErrorCount"
                    label="harvestRun.errors"
                    render={(r) =>
                      r.importErrorCount != null ? (
                        <Link to={`${path}/failed-records`}>
                          {r.importErrorCount}
                        </Link>
                      ) : null
                    }
                  />
                </SimpleShowLayout>
              </Grid>
              <Grid size={12}>
                <Typography variant="h6">
                  {translate("harvestRun.resultCounts")}
                </Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell />
                      {RESULT_COUNT_STATES.map((state) => (
                        <TableCell key={state}>
                          {translate(`harvestRun.${state}Count`)}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {RESULT_COUNT_KINDS.map((kind) => (
                      <TableRow key={kind.prefix}>
                        <TableCell component="th" scope="row">
                          {translate(`harvestRun.${kind.label}`)}
                        </TableCell>
                        {RESULT_COUNT_STATES.map((state) => (
                          <TableCell key={state}>
                            <NumberField
                              source={`${state}${kind.prefix}MetadataCount`}
                              label={false}
                            />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Grid>
            </Grid>
          </TabbedShowLayout.Tab>
          {[
            {
              resource: "DatasetMetadataRecord",
              label: "datasets",
              columns: ["title"],
            },
            {
              resource: "ServiceMetadataRecord",
              label: "services",
              columns: ["title"],
            },
            {
              resource: "ApplicationMetadataRecord",
              label: "applications",
              columns: ["title"],
            },
          ].map((tab) => (
            <TabbedShowLayout.Tab
              key={tab.resource}
              path={tab.resource}
              label={`harvestRun.${tab.label}`}
            >
              <ListGuesser
                resource={tab.resource}
                relatedResource={{ resource: "HarvestingJob", id: record.id }}
                storeKey={false}
                defaultSelectedColumns={tab.columns}
                refetchInterval={record.doneAt ? false : 5000}
              />
            </TabbedShowLayout.Tab>
          ))}
          <TabbedShowLayout.Tab
            path="failed-records"
            label="harvestRun.failedRecords"
          >
            <HarvestingRunMissingRecords />
          </TabbedShowLayout.Tab>
          {logTabAllowed && (
            <TabbedShowLayout.Tab path="log" label="harvestRun.logs">
              <ListHarvestingLog
                relatedResource={{ resource: "HarvestingJob", id: record.id }}
                storeKey={false}
                refetchInterval={record.doneAt ? false : 5000}
              />
            </TabbedShowLayout.Tab>
          )}
          <TabbedShowLayout.Tab
            path="diagnostics"
            label="harvestRun.diagnostics"
          >
            <SimpleShowLayout>
              <NumberField source="phase" />
              <NumberField source="totalSteps" />
              <NumberField source="doneSteps" />
              <DateField source="dateCreated" showTime emptyText="—" />
              <DateField source="doneAt" showTime emptyText="—" />
            </SimpleShowLayout>
            {/* what this run measures about its own work: the durations its
                records carried, the elapsed time, the throughput so far and
                the estimate of what is left - which stays worded as an
                estimate and is answered for no closed run (#1071) */}
            <Typography variant="h6">
              {translate("harvestRun.measurements")}
            </Typography>
            <SimpleShowLayout>
              <FunctionField
                source="elapsedSeconds"
                label="harvestRun.elapsed"
                render={(r) =>
                  r.elapsedSeconds != null
                    ? formatSeconds(r.elapsedSeconds)
                    : translate("harvestRun.notRecorded")
                }
              />
              <FunctionField
                source="fetchRecordDuration"
                label="harvestRun.measuredDownload"
                render={() =>
                  carriedDurations.current.fetchRecordDuration
                    ? formatMeasuredDuration(
                        carriedDurations.current.fetchRecordDuration,
                      )
                    : translate("harvestRun.notRecorded")
                }
              />
              <FunctionField
                source="mdMetadataFileToDbDuration"
                label="harvestRun.measuredDatabase"
                render={() =>
                  carriedDurations.current.mdMetadataFileToDbDuration
                    ? formatMeasuredDuration(
                        carriedDurations.current.mdMetadataFileToDbDuration,
                      )
                    : translate("harvestRun.notRecorded")
                }
              />
              <FunctionField
                source="recordsPerMinuteRunning"
                label="harvestRun.throughputRunning"
                render={(r) =>
                  r.recordsPerMinuteRunning != null
                    ? Math.round(r.recordsPerMinuteRunning)
                    : translate("harvestRun.notRecorded")
                }
              />
              <FunctionField
                source="estimatedSecondsRemaining"
                label="harvestRun.estimateRemaining"
                render={(r) =>
                  r.estimatedSecondsRemaining != null
                    ? formatSeconds(r.estimatedSecondsRemaining)
                    : translate("harvestRun.estimateUnknown")
                }
              />
              <DateField
                source="expectedDoneAt"
                label="harvestRun.expectedEnd"
                showTime
                emptyText={translate("harvestRun.estimateUnknown")}
              />
            </SimpleShowLayout>
            <Typography variant="caption" color="text.secondary">
              {translate("harvestRun.estimateNote")}
            </Typography>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Labeled label="harvestRun.downloadTimings">
                  <HarvestingJobTimingCharts selectedSerie="fetchRecordDurationSeries" />
                </Labeled>
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Labeled label="harvestRun.databaseTimings">
                  <HarvestingJobTimingCharts selectedSerie="dbDurationTotalSeries" />
                </Labeled>
              </Grid>
            </Grid>
          </TabbedShowLayout.Tab>
        </TabbedShowLayout>
      </Card>
      <Typography variant="caption" color="text.secondary">
        {translate(
          record.doneAt ? "harvestRun.terminated" : "harvestRun.refresh",
        )}
      </Typography>
    </Stack>
  );
};

export default HarvestingJobTabbedShowLayout;
