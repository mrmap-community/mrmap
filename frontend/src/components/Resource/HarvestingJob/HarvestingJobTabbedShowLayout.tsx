import {
  BooleanField,
  DateField,
  Labeled,
  Loading,
  NumberField,
  SimpleShowLayout,
  TabbedShowLayout,
  TextField,
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
import HarvestingJobTimingCharts from "./HarvestingJobTimingCharts";
import HarvestingRunSummary from "./HarvestingRunSummary";

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
                  <NumberField source="unhandledRecordsCount" />
                  <NumberField source="importErrorCount" />
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
