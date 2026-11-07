import { useRef } from "react";
import {
  BooleanField,
  DateField,
  FunctionField,
  Labeled,
  Loading,
  NumberField,
  SimpleShowLayout,
  TabbedShowLayout,
  TextField,
  useShowContext,
  useTranslate,
} from "react-admin";

import { Alert, Card, Grid, Stack, Typography } from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import HarvestingJobTimingCharts from "./HarvestingJobTimingCharts";
import HarvestingRunSummary from "./HarvestingRunSummary";
import { formatMeasuredDuration, formatSeconds } from "./runDurations";

const HarvestingJobTabbedShowLayout = () => {
  const { record, isPending, error } = useShowContext();
  const translate = useTranslate();
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
  return (
    <Stack spacing={2} sx={{ p: { xs: 1, md: 2 } }}>
      <HarvestingRunSummary />
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
                </SimpleShowLayout>
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="h6">
                  {translate("harvestRun.status")}
                </Typography>
                <SimpleShowLayout>
                  <TextField source="phaseLabel" label="harvestRun.phase" />
                  <NumberField source="totalRecords" />
                  <NumberField source="unhandledRecordsCount" />
                  <NumberField source="importErrorCount" />
                </SimpleShowLayout>
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
              resource: "TemporaryMdMetadataFile",
              label: "unhandled",
              columns: undefined,
            },
            { resource: "HarvestingLog", label: "logs", columns: undefined },
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
